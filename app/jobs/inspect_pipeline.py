from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select

from ..db import SessionLocal, init_db
from ..models import Event, EventMessage, Extraction, MessageProcessingState, RawMessage, RoutingDecision


def _fmt(value: Any, max_len: int = 120) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=True)
    else:
        text = str(value)
    if len(text) > max_len:
        return f"{text[: max_len - 3]}..."
    return text


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    if not rows:
        print("No rows found.")
        return

    widths = [len(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(_fmt(value)))

    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    divider_line = "-+-".join("-" * widths[i] for i in range(len(headers)))
    print(header_line)
    print(divider_line)
    for row in rows:
        print(" | ".join(_fmt(value).ljust(widths[i]) for i, value in enumerate(row)))


def _recent_overview(limit: int) -> None:
    headers = [
        "raw_id",
        "telegram_msg_id",
        "msg_time_utc",
        "topic",
        "impact",
        "conf",
        "breaking",
        "priority",
        "triage",
        "state",
        "event_id",
        "triage_rules",
    ]

    with SessionLocal() as db:
        stmt = (
            select(
                RawMessage.id,
                RawMessage.telegram_message_id,
                RawMessage.message_timestamp_utc,
                Extraction.topic,
                Extraction.impact_score,
                Extraction.confidence,
                Extraction.is_breaking,
                RoutingDecision.publish_priority,
                RoutingDecision.triage_action,
                MessageProcessingState.status,
                EventMessage.event_id,
                RoutingDecision.triage_rules,
            )
            .select_from(RawMessage)
            .outerjoin(MessageProcessingState, MessageProcessingState.raw_message_id == RawMessage.id)
            .outerjoin(Extraction, Extraction.raw_message_id == RawMessage.id)
            .outerjoin(RoutingDecision, RoutingDecision.raw_message_id == RawMessage.id)
            .outerjoin(EventMessage, EventMessage.raw_message_id == RawMessage.id)
            .order_by(RawMessage.id.desc())
            .limit(limit)
        )
        rows = [list(row) for row in db.execute(stmt).all()]
        _print_table(headers, rows)


def _detail(raw_message_id: int) -> None:
    with SessionLocal() as db:
        stmt = (
            select(
                RawMessage.id,
                RawMessage.source_channel_id,
                RawMessage.source_channel_name,
                RawMessage.telegram_message_id,
                RawMessage.message_timestamp_utc,
                RawMessage.created_at,
                RawMessage.raw_text,
                RawMessage.normalized_text,
                MessageProcessingState.status,
                MessageProcessingState.attempt_count,
                MessageProcessingState.last_error,
                Extraction.topic,
                Extraction.impact_score,
                Extraction.confidence,
                Extraction.is_breaking,
                Extraction.breaking_window,
                Extraction.event_fingerprint,
                Extraction.payload_json,
                Extraction.canonical_payload_json,
                RoutingDecision.publish_priority,
                RoutingDecision.requires_evidence,
                RoutingDecision.event_action,
                RoutingDecision.triage_action,
                RoutingDecision.triage_rules,
                RoutingDecision.flags,
                EventMessage.event_id,
                Event.event_fingerprint,
                Event.last_updated_at,
            )
            .select_from(RawMessage)
            .outerjoin(MessageProcessingState, MessageProcessingState.raw_message_id == RawMessage.id)
            .outerjoin(Extraction, Extraction.raw_message_id == RawMessage.id)
            .outerjoin(RoutingDecision, RoutingDecision.raw_message_id == RawMessage.id)
            .outerjoin(EventMessage, EventMessage.raw_message_id == RawMessage.id)
            .outerjoin(Event, Event.id == EventMessage.event_id)
            .where(RawMessage.id == raw_message_id)
        )
        row = db.execute(stmt).one_or_none()
        if row is None:
            print(f"No row found for raw_message_id={raw_message_id}")
            return

        (
            rid,
            source_channel_id,
            source_channel_name,
            telegram_message_id,
            message_timestamp_utc,
            created_at,
            raw_text,
            normalized_text,
            state,
            attempt_count,
            last_error,
            topic,
            impact_score,
            confidence,
            is_breaking,
            breaking_window,
            extraction_fingerprint,
            payload_json,
            canonical_payload_json,
            publish_priority,
            requires_evidence,
            event_action,
            triage_action,
            triage_rules,
            flags,
            event_id,
            event_fingerprint,
            event_last_updated_at,
        ) = row

        print(f"raw_message_id: {rid}")
        print(f"source_channel_id: {_fmt(source_channel_id)}")
        print(f"source_channel_name: {_fmt(source_channel_name)}")
        print(f"telegram_message_id: {_fmt(telegram_message_id)}")
        print(f"message_timestamp_utc: {_fmt(message_timestamp_utc)}")
        print(f"ingested_at: {_fmt(created_at)}")
        print()
        print("raw_text:")
        print(_fmt(raw_text, max_len=10_000))
        print()
        print("normalized_text:")
        print(_fmt(normalized_text, max_len=10_000))
        print()
        print("processing_state:")
        print(f"  status={_fmt(state)} attempt_count={_fmt(attempt_count)} last_error={_fmt(last_error, max_len=500)}")
        print()
        print("extraction:")
        print(
            f"  topic={_fmt(topic)} impact={_fmt(impact_score)} confidence={_fmt(confidence)} "
            f"breaking={_fmt(is_breaking)} window={_fmt(breaking_window)}"
        )
        print(f"  extraction_event_fingerprint={_fmt(extraction_fingerprint, max_len=500)}")
        print(f"  payload_json={_fmt(payload_json, max_len=1500)}")
        print(f"  canonical_payload_json={_fmt(canonical_payload_json, max_len=1500)}")
        print()
        print("routing_decision:")
        print(
            f"  publish_priority={_fmt(publish_priority)} requires_evidence={_fmt(requires_evidence)} "
            f"event_action={_fmt(event_action)} triage_action={_fmt(triage_action)}"
        )
        print(f"  triage_rules={_fmt(triage_rules, max_len=1000)}")
        print(f"  flags={_fmt(flags)}")
        print()
        print("event_link:")
        print(
            f"  event_id={_fmt(event_id)} event_fingerprint={_fmt(event_fingerprint, max_len=500)} "
            f"event_last_updated_at={_fmt(event_last_updated_at)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect pipeline data from raw ingest through extraction, triage, and event clustering."
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of recent raw messages to show in overview mode.")
    parser.add_argument(
        "--detail",
        type=int,
        default=None,
        metavar="RAW_MESSAGE_ID",
        help="Show expanded detail for a single raw_message_id.",
    )
    args = parser.parse_args()

    load_dotenv()
    init_db()

    if args.detail is not None:
        _detail(args.detail)
        return

    _recent_overview(limit=args.limit)


if __name__ == "__main__":
    main()

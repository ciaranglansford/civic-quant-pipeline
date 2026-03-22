from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, Engine, RowMapping, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.contexts.opportunity_memo import OPPORTUNITY_TOPICS
from app.contexts.opportunity_memo.input_builder import (
    build_opportunity_memo_input_pack,
    load_event_snapshots,
    rank_topic_candidates,
    topic_timeline,
)

from .db_mcp_contracts import (
    APP_DB_URL_ENV_VAR,
    DB_URL_ENV_VAR,
    DEFAULT_DATABASE_URL,
    LINEAGE_MAX_MESSAGES,
    READONLY_SQL_DEFAULT_MAX_ROWS,
    READONLY_SQL_HARD_MAX_ROWS,
)


_MUTATING_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|pragma|attach|detach|vacuum|reindex|analyze|begin|commit|rollback|truncate|lock|grant|revoke|copy|call|do|merge)\b",
    re.IGNORECASE,
)
_SELECT_INTO_RE = re.compile(r"\bselect\b[\s\S]*\binto\b", re.IGNORECASE)


@dataclass(frozen=True)
class ServiceError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class CivicquantDbMcpService:
    def __init__(self, database_url: str | None = None) -> None:
        load_dotenv()
        self.database_url = self._resolve_database_url(database_url=database_url)
        self._masked_database_url = self._mask_database_url(self.database_url)
        self._database_backend = make_url(self.database_url).get_backend_name().lower()
        self.engine = self._create_engine(database_url=self.database_url)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_event":
            return self.get_event(event_id=self._required_positive_int(arguments, "event_id"))
        if name == "get_raw_message":
            return self.get_raw_message(raw_message_id=self._required_positive_int(arguments, "raw_message_id"))
        if name == "get_event_lineage":
            return self.get_event_lineage(event_id=self._required_positive_int(arguments, "event_id"))
        if name == "compare_extraction_to_event":
            return self.compare_extraction_to_event(
                raw_message_id=self._required_positive_int(arguments, "raw_message_id")
            )
        if name == "find_duplicate_candidate_events":
            return self.find_duplicate_candidate_events(
                event_id=self._required_positive_int(arguments, "event_id")
            )
        if name == "run_readonly_sql":
            query = arguments.get("query")
            if not isinstance(query, str):
                raise ServiceError(
                    code="invalid_arguments",
                    message="'query' must be a string.",
                )
            max_rows = arguments.get("max_rows", READONLY_SQL_DEFAULT_MAX_ROWS)
            if not isinstance(max_rows, int):
                raise ServiceError(code="invalid_arguments", message="'max_rows' must be an integer.")
            return self.run_readonly_sql(query=query, max_rows=max_rows)
        if name == "rank_topic_opportunities":
            start_time = self._required_datetime(arguments, "start_time")
            end_time = self._required_datetime(arguments, "end_time")
            topic_universe = self._required_topic_universe(arguments, "topic_universe")
            limit = arguments.get("limit", 5)
            if not isinstance(limit, int):
                raise ServiceError(code="invalid_arguments", message="'limit' must be an integer.")
            return self.rank_topic_opportunities(
                start_time=start_time,
                end_time=end_time,
                topic_universe=topic_universe,
                limit=limit,
            )
        if name == "build_opportunity_memo_input":
            start_time = self._required_datetime(arguments, "start_time")
            end_time = self._required_datetime(arguments, "end_time")
            topic = self._required_topic(arguments, "topic")
            return self.build_opportunity_memo_input(
                start_time=start_time,
                end_time=end_time,
                topic=topic,
            )
        if name == "get_topic_timeline":
            start_time = self._required_datetime(arguments, "start_time")
            end_time = self._required_datetime(arguments, "end_time")
            topic = self._required_topic(arguments, "topic")
            limit = arguments.get("limit", 50)
            if not isinstance(limit, int):
                raise ServiceError(code="invalid_arguments", message="'limit' must be an integer.")
            return self.get_topic_timeline(
                start_time=start_time,
                end_time=end_time,
                topic=topic,
                limit=limit,
            )
        if name == "get_topic_driver_pack":
            start_time = self._required_datetime(arguments, "start_time")
            end_time = self._required_datetime(arguments, "end_time")
            topic = self._required_topic(arguments, "topic")
            return self.get_topic_driver_pack(
                start_time=start_time,
                end_time=end_time,
                topic=topic,
            )
        raise ServiceError(code="unknown_tool", message=f"Unknown tool '{name}'.")

    def get_event(self, *, event_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            event_row = self._fetchone(
                conn,
                """
                SELECT
                    e.id,
                    e.event_identity_fingerprint_v2,
                    e.event_fingerprint,
                    e.topic,
                    e.summary_1_sentence,
                    e.impact_score,
                    e.is_breaking,
                    e.breaking_window,
                    e.event_time,
                    e.event_time_bucket,
                    e.action_class,
                    e.claim_hash,
                    e.canonical_payload_hash,
                    e.review_required,
                    e.review_reason,
                    e.last_updated_at,
                    e.latest_extraction_id,
                    x.topic AS latest_extraction_topic,
                    x.event_time AS latest_extraction_event_time,
                    x.claim_hash AS latest_extraction_claim_hash,
                    x.canonical_payload_hash AS latest_extraction_canonical_payload_hash
                FROM events AS e
                LEFT JOIN extractions AS x ON x.id = e.latest_extraction_id
                WHERE e.id = :event_id
                """,
                {"event_id": event_id},
            )
            if event_row is None:
                raise ServiceError(code="not_found", message=f"Event {event_id} was not found.")

            link_rows = self._fetchall(
                conn,
                """
                SELECT raw_message_id
                FROM event_messages
                WHERE event_id = :event_id
                ORDER BY linked_at ASC, id ASC
                """,
                {"event_id": event_id},
            )

        linked_raw_ids = [int(row["raw_message_id"]) for row in link_rows]
        return self._jsonify_payload({
            "ok": True,
            "database_url": self._masked_database_url,
            "event": self._row_to_dict(event_row),
            "linked_raw_message_ids": linked_raw_ids,
            "message_count": len(linked_raw_ids),
        })

    def get_raw_message(self, *, raw_message_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            raw_row = self._fetchone(
                conn,
                """
                SELECT
                    id,
                    source_channel_id,
                    source_channel_name,
                    telegram_message_id,
                    message_timestamp_utc,
                    raw_text,
                    normalized_text,
                    created_at
                FROM raw_messages
                WHERE id = :raw_message_id
                """,
                {"raw_message_id": raw_message_id},
            )
            if raw_row is None:
                raise ServiceError(code="not_found", message=f"Raw message {raw_message_id} was not found.")

            extraction_row = self._fetchone(
                conn,
                """
                SELECT
                    id,
                    raw_message_id,
                    topic,
                    event_time,
                    impact_score,
                    confidence,
                    is_breaking,
                    breaking_window,
                    event_fingerprint,
                    event_identity_fingerprint_v2,
                    claim_hash,
                    canonical_payload_hash,
                    payload_json,
                    canonical_payload_json,
                    metadata_json,
                    created_at
                FROM extractions
                WHERE raw_message_id = :raw_message_id
                """,
                {"raw_message_id": raw_message_id},
            )

            routing_row = self._fetchone(
                conn,
                """
                SELECT
                    id,
                    raw_message_id,
                    store_to,
                    publish_priority,
                    requires_evidence,
                    event_action,
                    triage_action,
                    triage_rules,
                    flags,
                    created_at
                FROM routing_decisions
                WHERE raw_message_id = :raw_message_id
                """,
                {"raw_message_id": raw_message_id},
            )

            event_link_rows = self._fetchall(
                conn,
                """
                SELECT
                    em.event_id,
                    em.linked_at,
                    e.topic AS event_topic,
                    e.summary_1_sentence AS event_summary_1_sentence,
                    e.last_updated_at AS event_last_updated_at
                FROM event_messages AS em
                LEFT JOIN events AS e ON e.id = em.event_id
                WHERE em.raw_message_id = :raw_message_id
                ORDER BY em.linked_at ASC, em.id ASC
                """,
                {"raw_message_id": raw_message_id},
            )

        return self._jsonify_payload({
            "ok": True,
            "database_url": self._masked_database_url,
            "raw_message": {
                "id": int(raw_row["id"]),
                "source_channel_id": raw_row["source_channel_id"],
                "source_channel_name": raw_row["source_channel_name"],
                "telegram_message_id": raw_row["telegram_message_id"],
                "message_timestamp_utc": raw_row["message_timestamp_utc"],
                "created_at": raw_row["created_at"],
                "raw_text_preview": self._preview_text(raw_row["raw_text"]),
                "raw_text_length": self._safe_len(raw_row["raw_text"]),
                "normalized_text_preview": self._preview_text(raw_row["normalized_text"]),
                "normalized_text_length": self._safe_len(raw_row["normalized_text"]),
            },
            "extraction": self._extraction_brief(extraction_row),
            "routing_decision": self._routing_brief(routing_row),
            "event_links": [self._row_to_dict(row) for row in event_link_rows],
        })

    def get_event_lineage(self, *, event_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            event_row = self._fetchone(
                conn,
                """
                SELECT
                    id,
                    topic,
                    summary_1_sentence,
                    event_time,
                    impact_score,
                    event_identity_fingerprint_v2,
                    claim_hash,
                    canonical_payload_hash,
                    latest_extraction_id,
                    last_updated_at
                FROM events
                WHERE id = :event_id
                """,
                {"event_id": event_id},
            )
            if event_row is None:
                raise ServiceError(code="not_found", message=f"Event {event_id} was not found.")

            total_messages = self._fetchone(
                conn,
                "SELECT COUNT(*) AS c FROM event_messages WHERE event_id = :event_id",
                {"event_id": event_id},
            )

            lineage_rows = self._fetchall(
                conn,
                """
                SELECT
                    em.id AS event_message_id,
                    em.linked_at AS event_linked_at,
                    r.id AS raw_message_id,
                    r.source_channel_id,
                    r.source_channel_name,
                    r.telegram_message_id,
                    r.message_timestamp_utc,
                    r.raw_text,
                    r.normalized_text,
                    x.id AS extraction_id,
                    x.topic AS extraction_topic,
                    x.event_time AS extraction_event_time,
                    x.impact_score AS extraction_impact_score,
                    x.confidence AS extraction_confidence,
                    x.is_breaking AS extraction_is_breaking,
                    x.breaking_window AS extraction_breaking_window,
                    x.event_fingerprint AS extraction_event_fingerprint,
                    x.event_identity_fingerprint_v2 AS extraction_event_identity_fingerprint_v2,
                    x.claim_hash AS extraction_claim_hash,
                    x.canonical_payload_hash AS extraction_canonical_payload_hash,
                    x.payload_json AS extraction_payload_json,
                    x.canonical_payload_json AS extraction_canonical_payload_json,
                    x.metadata_json AS extraction_metadata_json,
                    rd.id AS routing_decision_id,
                    rd.store_to AS routing_store_to,
                    rd.publish_priority AS routing_publish_priority,
                    rd.requires_evidence AS routing_requires_evidence,
                    rd.event_action AS routing_event_action,
                    rd.triage_action AS routing_triage_action,
                    rd.triage_rules AS routing_triage_rules,
                    rd.flags AS routing_flags
                FROM event_messages AS em
                JOIN raw_messages AS r ON r.id = em.raw_message_id
                LEFT JOIN extractions AS x ON x.raw_message_id = r.id
                LEFT JOIN routing_decisions AS rd ON rd.raw_message_id = r.id
                WHERE em.event_id = :event_id
                ORDER BY em.linked_at ASC, em.id ASC
                LIMIT :lineage_limit
                """,
                {
                    "event_id": event_id,
                    "lineage_limit": LINEAGE_MAX_MESSAGES,
                },
            )

        messages: list[dict[str, Any]] = []
        for row in lineage_rows:
            payload = self._best_payload_for_join_row(row)
            messages.append(
                {
                    "event_message": {
                        "id": row["event_message_id"],
                        "linked_at": row["event_linked_at"],
                    },
                    "raw_message": {
                        "id": row["raw_message_id"],
                        "source_channel_id": row["source_channel_id"],
                        "source_channel_name": row["source_channel_name"],
                        "telegram_message_id": row["telegram_message_id"],
                        "message_timestamp_utc": row["message_timestamp_utc"],
                        "raw_text_preview": self._preview_text(row["raw_text"]),
                        "normalized_text_preview": self._preview_text(row["normalized_text"]),
                    },
                    "extraction": {
                        "id": row["extraction_id"],
                        "topic": row["extraction_topic"],
                        "event_time": row["extraction_event_time"],
                        "impact_score": row["extraction_impact_score"],
                        "confidence": row["extraction_confidence"],
                        "is_breaking": row["extraction_is_breaking"],
                        "breaking_window": row["extraction_breaking_window"],
                        "event_fingerprint": row["extraction_event_fingerprint"],
                        "event_identity_fingerprint_v2": row["extraction_event_identity_fingerprint_v2"],
                        "claim_hash": row["extraction_claim_hash"],
                        "canonical_payload_hash": row["extraction_canonical_payload_hash"],
                        "summary_1_sentence": payload.get("summary_1_sentence") if isinstance(payload, dict) else None,
                    },
                    "routing_decision": {
                        "id": row["routing_decision_id"],
                        "store_to": self._try_parse_json(row["routing_store_to"]),
                        "publish_priority": row["routing_publish_priority"],
                        "requires_evidence": row["routing_requires_evidence"],
                        "event_action": row["routing_event_action"],
                        "triage_action": row["routing_triage_action"],
                        "triage_rules": self._try_parse_json(row["routing_triage_rules"]),
                        "flags": self._try_parse_json(row["routing_flags"]),
                    },
                }
            )

        total_count = int(total_messages["c"]) if total_messages is not None else len(messages)
        return self._jsonify_payload({
            "ok": True,
            "database_url": self._masked_database_url,
            "event": self._row_to_dict(event_row),
            "lineage_messages": messages,
            "lineage_count": len(messages),
            "lineage_total_count": total_count,
            "lineage_truncated": total_count > len(messages),
        })

    def compare_extraction_to_event(self, *, raw_message_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            extraction_row = self._fetchone(
                conn,
                """
                SELECT
                    id,
                    raw_message_id,
                    topic,
                    event_time,
                    impact_score,
                    confidence,
                    is_breaking,
                    breaking_window,
                    event_fingerprint,
                    event_identity_fingerprint_v2,
                    claim_hash,
                    canonical_payload_hash,
                    payload_json,
                    canonical_payload_json,
                    metadata_json
                FROM extractions
                WHERE raw_message_id = :raw_message_id
                """,
                {"raw_message_id": raw_message_id},
            )
            if extraction_row is None:
                raise ServiceError(
                    code="not_found",
                    message=f"No extraction row found for raw_message_id {raw_message_id}.",
                )

            event_rows = self._fetchall(
                conn,
                """
                SELECT
                    e.id,
                    e.topic,
                    e.summary_1_sentence,
                    e.event_time,
                    e.impact_score,
                    e.is_breaking,
                    e.breaking_window,
                    e.event_identity_fingerprint_v2,
                    e.claim_hash,
                    e.canonical_payload_hash,
                    e.action_class,
                    e.event_time_bucket,
                    e.last_updated_at
                FROM events AS e
                JOIN event_messages AS em ON em.event_id = e.id
                WHERE em.raw_message_id = :raw_message_id
                ORDER BY em.linked_at ASC, em.id ASC
                """,
                {"raw_message_id": raw_message_id},
            )

        event_ids = [int(row["id"]) for row in event_rows]
        if not event_rows:
            return self._jsonify_payload({
                "ok": True,
                "database_url": self._masked_database_url,
                "raw_message_id": raw_message_id,
                "event_ids": [],
                "comparison": {
                    "status": "no_linked_event",
                    "matches": [],
                    "mismatches": [],
                },
            })

        primary_event = event_rows[0]
        payload = self._best_payload(extraction_row)
        metadata = self._as_dict(self._try_parse_json(extraction_row["metadata_json"]))

        extraction_summary = payload.get("summary_1_sentence") if isinstance(payload, dict) else None
        extraction_identity = (
            extraction_row["event_identity_fingerprint_v2"]
            or extraction_row["event_fingerprint"]
            or payload.get("event_fingerprint")
        )
        extraction_action_class = metadata.get("action_class")
        extraction_time_bucket = metadata.get("event_time_bucket")

        comparisons = [
            self._compare_value("topic", extraction_row["topic"], primary_event["topic"]),
            self._compare_value("event_time", extraction_row["event_time"], primary_event["event_time"]),
            self._compare_value("impact_score", extraction_row["impact_score"], primary_event["impact_score"]),
            self._compare_value("is_breaking", extraction_row["is_breaking"], primary_event["is_breaking"]),
            self._compare_value("breaking_window", extraction_row["breaking_window"], primary_event["breaking_window"]),
            self._compare_value("summary_1_sentence", extraction_summary, primary_event["summary_1_sentence"]),
            self._compare_value(
                "event_identity_fingerprint_v2",
                extraction_identity,
                primary_event["event_identity_fingerprint_v2"],
            ),
            self._compare_value("claim_hash", extraction_row["claim_hash"], primary_event["claim_hash"]),
            self._compare_value(
                "canonical_payload_hash",
                extraction_row["canonical_payload_hash"],
                primary_event["canonical_payload_hash"],
            ),
            self._compare_value("action_class", extraction_action_class, primary_event["action_class"]),
            self._compare_value("event_time_bucket", extraction_time_bucket, primary_event["event_time_bucket"]),
        ]

        matches = [item for item in comparisons if item["match"]]
        mismatches = [item for item in comparisons if not item["match"]]

        return self._jsonify_payload({
            "ok": True,
            "database_url": self._masked_database_url,
            "raw_message_id": raw_message_id,
            "event_ids": event_ids,
            "primary_event_id": int(primary_event["id"]),
            "comparison": {
                "status": "consistent" if not mismatches else "inconsistent",
                "match_count": len(matches),
                "mismatch_count": len(mismatches),
                "matches": matches,
                "mismatches": mismatches,
            },
        })

    def find_duplicate_candidate_events(self, *, event_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            base_event = self._fetchone(
                conn,
                """
                SELECT
                    id,
                    topic,
                    summary_1_sentence,
                    event_time,
                    is_breaking,
                    event_identity_fingerprint_v2,
                    claim_hash,
                    canonical_payload_hash,
                    latest_extraction_id
                FROM events
                WHERE id = :event_id
                """,
                {"event_id": event_id},
            )
            if base_event is None:
                raise ServiceError(code="not_found", message=f"Event {event_id} was not found.")

            candidate_rows = self._fetch_duplicate_candidates(conn=conn, base_event=base_event)
            extraction_by_id = self._fetch_extractions_for_candidates(conn=conn, candidate_rows=candidate_rows)
            base_latest_extraction = extraction_by_id.get(base_event["latest_extraction_id"])
            if base_latest_extraction is None and isinstance(base_event["latest_extraction_id"], int):
                base_latest_extraction = self._fetchone(
                    conn,
                    "SELECT id, canonical_payload_json, payload_json FROM extractions WHERE id = :extraction_id",
                    {"extraction_id": base_event["latest_extraction_id"]},
                )

        base_payload = self._payload_for_extraction_row(base_latest_extraction)
        base_entities = self._entity_signature(base_payload)
        base_keywords = self._keywords(base_payload)

        window_hours = 6 if bool(base_event["is_breaking"]) else 24
        base_time = self._parse_datetime(base_event["event_time"])
        base_summary = self._normalized_text(base_event["summary_1_sentence"])

        scored: list[dict[str, Any]] = []
        for candidate in candidate_rows:
            candidate_payload = self._payload_for_extraction_row(
                extraction_by_id.get(candidate["latest_extraction_id"])
            )
            candidate_entities = self._entity_signature(candidate_payload)
            candidate_keywords = self._keywords(candidate_payload)

            same_identity = bool(
                base_event["event_identity_fingerprint_v2"]
                and candidate["event_identity_fingerprint_v2"]
                and base_event["event_identity_fingerprint_v2"] == candidate["event_identity_fingerprint_v2"]
            )
            same_claim_hash = bool(
                base_event["claim_hash"]
                and candidate["claim_hash"]
                and base_event["claim_hash"] == candidate["claim_hash"]
            )
            same_payload_hash = bool(
                base_event["canonical_payload_hash"]
                and candidate["canonical_payload_hash"]
                and base_event["canonical_payload_hash"] == candidate["canonical_payload_hash"]
            )

            summary_ratio = self._summary_ratio(base_summary, self._normalized_text(candidate["summary_1_sentence"]))
            shared_entities = len(base_entities & candidate_entities)
            shared_keywords = len(base_keywords & candidate_keywords)

            hours_apart: float | None = None
            within_window = False
            if base_time is not None:
                candidate_time = self._parse_datetime(candidate["event_time"])
                if candidate_time is not None:
                    hours_apart = abs((candidate_time - base_time).total_seconds()) / 3600.0
                    within_window = hours_apart <= window_hours

            score = 0
            reasons: list[str] = []
            if same_identity:
                score += 8
                reasons.append("same_event_identity_fingerprint_v2")
            if same_claim_hash:
                score += 5
                reasons.append("same_claim_hash")
            if same_payload_hash:
                score += 4
                reasons.append("same_canonical_payload_hash")
            if summary_ratio >= 0.90:
                score += 2
                reasons.append("summary_similarity_ge_0_90")
            elif summary_ratio >= 0.80:
                score += 1
                reasons.append("summary_similarity_ge_0_80")
            if shared_entities >= 2:
                score += 2
                reasons.append("shared_entities_ge_2")
            elif shared_entities == 1:
                score += 1
                reasons.append("shared_entities_eq_1")
            if shared_keywords >= 2:
                score += 1
                reasons.append("shared_keywords_ge_2")
            if within_window:
                score += 1
                reasons.append("within_time_window")

            if score < 3:
                continue

            if score >= 9:
                likelihood = "high"
            elif score >= 5:
                likelihood = "medium"
            else:
                likelihood = "low"

            scored.append(
                {
                    "event_id": int(candidate["id"]),
                    "topic": candidate["topic"],
                    "summary_1_sentence": candidate["summary_1_sentence"],
                    "event_time": candidate["event_time"],
                    "last_updated_at": candidate["last_updated_at"],
                    "score": score,
                    "duplicate_likelihood": likelihood,
                    "signals": {
                        "same_event_identity_fingerprint_v2": same_identity,
                        "same_claim_hash": same_claim_hash,
                        "same_canonical_payload_hash": same_payload_hash,
                        "summary_similarity_ratio": round(summary_ratio, 3),
                        "shared_entity_count": shared_entities,
                        "shared_keyword_count": shared_keywords,
                        "hours_apart": round(hours_apart, 3) if hours_apart is not None else None,
                        "within_time_window": within_window,
                    },
                    "reason_codes": reasons,
                }
            )

        scored.sort(
            key=lambda row: (
                -int(row["score"]),
                row["signals"]["hours_apart"] if row["signals"]["hours_apart"] is not None else 9999.0,
                int(row["event_id"]),
            )
        )
        top_candidates = scored[:20]

        return self._jsonify_payload({
            "ok": True,
            "database_url": self._masked_database_url,
            "base_event_id": event_id,
            "window_hours": window_hours,
            "candidate_scan_count": len(candidate_rows),
            "candidate_match_count": len(top_candidates),
            "candidates": top_candidates,
        })

    def rank_topic_opportunities(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        topic_universe: list[str],
        limit: int,
    ) -> dict[str, Any]:
        if start_time >= end_time:
            raise ServiceError(code="invalid_arguments", message="'start_time' must be earlier than 'end_time'.")

        with self._session() as db:
            ranked = rank_topic_candidates(
                db,
                start_time=start_time,
                end_time=end_time,
                topic_universe=topic_universe,
                limit=max(1, min(limit, 20)),
                recent_memo_topics=set(),
            )

        return self._jsonify_payload(
            {
                "ok": True,
                "database_url": self._masked_database_url,
                "window": {
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                },
                "topics": [row.model_dump(mode="json") for row in ranked],
            }
        )

    def build_opportunity_memo_input(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        topic: str,
    ) -> dict[str, Any]:
        if start_time >= end_time:
            raise ServiceError(code="invalid_arguments", message="'start_time' must be earlier than 'end_time'.")

        with self._session() as db:
            ranked = rank_topic_candidates(
                db,
                start_time=start_time,
                end_time=end_time,
                topic_universe=[topic],
                limit=1,
                recent_memo_topics=set(),
            )
            topic_score = float(ranked[0].topic_score) if ranked else 0.0
            topic_breakdown = (
                ranked[0].breakdown.model_dump(mode="json")
                if ranked
                else {
                    "normalized_event_count": 0.0,
                    "normalized_weighted_impact": 0.0,
                    "normalized_novelty": 0.0,
                    "normalized_coherence": 0.0,
                    "normalized_actionability": 0.0,
                }
            )
            pack, _topic_events = build_opportunity_memo_input_pack(
                db,
                start_time=start_time,
                end_time=end_time,
                topic=topic,
                topic_score=topic_score,
                selection_reason="mcp_build_input",
                topic_breakdown=topic_breakdown,
            )

        return self._jsonify_payload(
            {
                "ok": True,
                "database_url": self._masked_database_url,
                "input_pack": pack.model_dump(mode="json"),
            }
        )

    def get_topic_timeline(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        topic: str,
        limit: int,
    ) -> dict[str, Any]:
        if start_time >= end_time:
            raise ServiceError(code="invalid_arguments", message="'start_time' must be earlier than 'end_time'.")

        with self._session() as db:
            snapshots = load_event_snapshots(db, start_time=start_time, end_time=end_time)
            timeline = topic_timeline(
                snapshots=snapshots,
                topic=topic,
                limit=max(1, min(limit, 200)),
            )

        return self._jsonify_payload(
            {
                "ok": True,
                "database_url": self._masked_database_url,
                "window": {
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                },
                "topic": topic,
                "timeline": [row.model_dump(mode="json") for row in timeline],
            }
        )

    def get_topic_driver_pack(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        topic: str,
    ) -> dict[str, Any]:
        if start_time >= end_time:
            raise ServiceError(code="invalid_arguments", message="'start_time' must be earlier than 'end_time'.")

        with self._session() as db:
            ranked = rank_topic_candidates(
                db,
                start_time=start_time,
                end_time=end_time,
                topic_universe=[topic],
                limit=1,
                recent_memo_topics=set(),
            )
            topic_score = float(ranked[0].topic_score) if ranked else 0.0
            topic_breakdown = (
                ranked[0].breakdown.model_dump(mode="json")
                if ranked
                else {
                    "normalized_event_count": 0.0,
                    "normalized_weighted_impact": 0.0,
                    "normalized_novelty": 0.0,
                    "normalized_coherence": 0.0,
                    "normalized_actionability": 0.0,
                }
            )
            pack, _topic_events = build_opportunity_memo_input_pack(
                db,
                start_time=start_time,
                end_time=end_time,
                topic=topic,
                topic_score=topic_score,
                selection_reason="mcp_driver_pack",
                topic_breakdown=topic_breakdown,
            )

        return self._jsonify_payload(
            {
                "ok": True,
                "database_url": self._masked_database_url,
                "topic": topic,
                "drivers": [
                    row.model_dump(mode="json")
                    for row in pack.candidate_driver_groups
                ],
                "selected_primary_driver": (
                    pack.selected_primary_driver.model_dump(mode="json")
                    if pack.selected_primary_driver is not None
                    else None
                ),
            }
        )

    def run_readonly_sql(self, *, query: str, max_rows: int = READONLY_SQL_DEFAULT_MAX_ROWS) -> dict[str, Any]:
        safe_query = self._validate_readonly_sql(query=query)
        row_cap = max(1, min(max_rows, READONLY_SQL_HARD_MAX_ROWS))

        with self._connect() as conn:
            try:
                result = conn.execute(text(safe_query))
                rows = result.mappings().fetchmany(row_cap + 1)
                columns = list(result.keys())
            except SQLAlchemyError as exc:
                raise ServiceError(
                    code="sql_error",
                    message=f"Database query failed: {exc}",
                ) from exc

        truncated = len(rows) > row_cap
        if truncated:
            rows = rows[:row_cap]

        return self._jsonify_payload({
            "ok": True,
            "database_url": self._masked_database_url,
            "query": safe_query,
            "max_rows": row_cap,
            "row_count": len(rows),
            "truncated": truncated,
            "columns": columns,
            "rows": [self._row_to_dict(row) for row in rows],
        })

    def _resolve_database_url(self, *, database_url: str | None) -> str:
        candidate = database_url or os.getenv(DB_URL_ENV_VAR) or os.getenv(APP_DB_URL_ENV_VAR)
        if candidate and candidate.strip():
            return candidate.strip()

        settings = get_settings()
        if settings.database_url.strip():
            return settings.database_url.strip()
        return DEFAULT_DATABASE_URL

    def _create_engine(self, *, database_url: str) -> Engine:
        connect_args: dict[str, Any] = {}
        backend = make_url(database_url).get_backend_name().lower()
        if backend in {"postgres", "postgresql"}:
            # Defense in depth: keep every transaction read-only on postgres.
            connect_args["options"] = "-c default_transaction_read_only=on"
        return create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)

    @contextmanager
    def _connect(self) -> Connection:
        try:
            with self.engine.connect() as conn:
                if self._database_backend in {"postgres", "postgresql"}:
                    conn.execute(text("SET TRANSACTION READ ONLY"))
                yield conn
        except SQLAlchemyError as exc:
            raise ServiceError(
                code="db_connection_error",
                message=f"Failed to open database connection: {exc}",
                details={
                    "database_url": self._masked_database_url,
                    "hint": f"Set {DB_URL_ENV_VAR} (or {APP_DB_URL_ENV_VAR}) to a readable database URL.",
                },
            ) from exc

    @contextmanager
    def _session(self) -> OrmSession:
        with self._connect() as conn:
            with OrmSession(bind=conn, future=True) as db:
                yield db

    def _fetchone(
        self,
        conn: Connection,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> RowMapping | None:
        return conn.execute(text(query), params or {}).mappings().first()

    def _fetchall(
        self,
        conn: Connection,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[RowMapping]:
        return list(conn.execute(text(query), params or {}).mappings().all())

    def _mask_database_url(self, database_url: str) -> str:
        try:
            return make_url(database_url).render_as_string(hide_password=True)
        except Exception:  # noqa: BLE001
            return database_url

    def _required_positive_int(self, arguments: dict[str, Any], key: str) -> int:
        value = arguments.get(key)
        if not isinstance(value, int) or value < 1:
            raise ServiceError(
                code="invalid_arguments",
                message=f"'{key}' must be a positive integer.",
            )
        return value

    def _required_datetime(self, arguments: dict[str, Any], key: str) -> datetime:
        raw_value = arguments.get(key)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ServiceError(code="invalid_arguments", message=f"'{key}' must be a datetime string.")
        value = raw_value.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ServiceError(code="invalid_arguments", message=f"'{key}' must be ISO datetime.") from exc
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _required_topic(self, arguments: dict[str, Any], key: str) -> str:
        raw_value = arguments.get(key)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ServiceError(code="invalid_arguments", message=f"'{key}' must be a non-empty string.")
        topic = raw_value.strip()
        if topic not in OPPORTUNITY_TOPICS:
            raise ServiceError(
                code="invalid_arguments",
                message=f"'{key}' must be one of {','.join(OPPORTUNITY_TOPICS)}.",
            )
        return topic

    def _required_topic_universe(self, arguments: dict[str, Any], key: str) -> list[str]:
        raw_value = arguments.get(key)
        if not isinstance(raw_value, list) or not raw_value:
            raise ServiceError(code="invalid_arguments", message=f"'{key}' must be a non-empty list of topics.")
        topics: list[str] = []
        seen: set[str] = set()
        for item in raw_value:
            if not isinstance(item, str) or not item.strip():
                raise ServiceError(code="invalid_arguments", message=f"'{key}' must contain non-empty strings.")
            topic = item.strip()
            if topic not in OPPORTUNITY_TOPICS:
                raise ServiceError(
                    code="invalid_arguments",
                    message=f"'{key}' values must be from {','.join(OPPORTUNITY_TOPICS)}.",
                )
            if topic in seen:
                continue
            seen.add(topic)
            topics.append(topic)
        if not topics:
            raise ServiceError(code="invalid_arguments", message=f"'{key}' must include at least one topic.")
        return topics

    def _row_to_dict(self, row: Mapping[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in row.items():
            payload[key] = self._to_json_value(value)
        return payload

    def _jsonify_payload(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): self._jsonify_payload(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonify_payload(item) for item in value]
        if isinstance(value, tuple):
            return [self._jsonify_payload(item) for item in value]
        return self._to_json_value(value)

    def _to_json_value(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return value.hex()
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        parsed = self._try_parse_json(value)
        return parsed

    def _try_parse_json(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list, int, float, bool)):
            return value
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            return value
        if stripped[0] not in {"{", "["}:
            return value
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    def _preview_text(self, value: Any, max_chars: int = 320) -> str | None:
        if not isinstance(value, str):
            return None
        if len(value) <= max_chars:
            return value
        return value[: max_chars - 3] + "..."

    def _safe_len(self, value: Any) -> int | None:
        if not isinstance(value, str):
            return None
        return len(value)

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _best_payload(self, extraction_row: Mapping[str, Any]) -> dict[str, Any]:
        canonical = self._try_parse_json(extraction_row["canonical_payload_json"])
        if isinstance(canonical, dict):
            return canonical
        raw = self._try_parse_json(extraction_row["payload_json"])
        if isinstance(raw, dict):
            return raw
        return {}

    def _payload_for_extraction_row(self, extraction_row: Mapping[str, Any] | None) -> dict[str, Any]:
        if extraction_row is None:
            return {}
        canonical = self._try_parse_json(extraction_row["canonical_payload_json"])
        if isinstance(canonical, dict):
            return canonical
        raw = self._try_parse_json(extraction_row["payload_json"])
        if isinstance(raw, dict):
            return raw
        return {}

    def _best_payload_for_join_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        canonical = self._try_parse_json(row["extraction_canonical_payload_json"])
        if isinstance(canonical, dict):
            return canonical
        raw = self._try_parse_json(row["extraction_payload_json"])
        if isinstance(raw, dict):
            return raw
        return {}

    def _extraction_brief(self, extraction_row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if extraction_row is None:
            return None
        payload = self._best_payload(extraction_row)
        metadata = self._as_dict(self._try_parse_json(extraction_row["metadata_json"]))
        return {
            "id": extraction_row["id"],
            "raw_message_id": extraction_row["raw_message_id"],
            "topic": extraction_row["topic"],
            "event_time": extraction_row["event_time"],
            "impact_score": extraction_row["impact_score"],
            "confidence": extraction_row["confidence"],
            "is_breaking": extraction_row["is_breaking"],
            "breaking_window": extraction_row["breaking_window"],
            "event_fingerprint": extraction_row["event_fingerprint"],
            "event_identity_fingerprint_v2": extraction_row["event_identity_fingerprint_v2"],
            "claim_hash": extraction_row["claim_hash"],
            "canonical_payload_hash": extraction_row["canonical_payload_hash"],
            "summary_1_sentence": payload.get("summary_1_sentence"),
            "keywords": payload.get("keywords"),
            "entities": payload.get("entities"),
            "metadata_action_class": metadata.get("action_class"),
            "metadata_event_time_bucket": metadata.get("event_time_bucket"),
            "created_at": extraction_row["created_at"],
        }

    def _routing_brief(self, routing_row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if routing_row is None:
            return None
        return {
            "id": routing_row["id"],
            "raw_message_id": routing_row["raw_message_id"],
            "store_to": self._try_parse_json(routing_row["store_to"]),
            "publish_priority": routing_row["publish_priority"],
            "requires_evidence": routing_row["requires_evidence"],
            "event_action": routing_row["event_action"],
            "triage_action": routing_row["triage_action"],
            "triage_rules": self._try_parse_json(routing_row["triage_rules"]),
            "flags": self._try_parse_json(routing_row["flags"]),
            "created_at": routing_row["created_at"],
        }

    def _compare_value(self, field: str, extraction_value: Any, event_value: Any) -> dict[str, Any]:
        left = self._to_json_value(extraction_value)
        right = self._to_json_value(event_value)

        match = False
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            match = abs(float(left) - float(right)) <= 0.01
        else:
            match = left == right

        return {
            "field": field,
            "match": match,
            "extraction_value": left,
            "event_value": right,
        }

    def _fetch_duplicate_candidates(
        self,
        *,
        conn: Connection,
        base_event: Mapping[str, Any],
    ) -> list[RowMapping]:
        if base_event["topic"]:
            return self._fetchall(
                conn,
                """
                SELECT
                    id,
                    topic,
                    summary_1_sentence,
                    event_time,
                    event_identity_fingerprint_v2,
                    claim_hash,
                    canonical_payload_hash,
                    latest_extraction_id,
                    last_updated_at
                FROM events
                WHERE id != :base_event_id AND topic = :base_topic
                ORDER BY last_updated_at DESC, id DESC
                LIMIT 250
                """,
                {"base_event_id": base_event["id"], "base_topic": base_event["topic"]},
            )

        return self._fetchall(
            conn,
            """
            SELECT
                id,
                topic,
                summary_1_sentence,
                event_time,
                event_identity_fingerprint_v2,
                claim_hash,
                canonical_payload_hash,
                latest_extraction_id,
                last_updated_at
            FROM events
            WHERE id != :base_event_id
            ORDER BY last_updated_at DESC, id DESC
            LIMIT 250
            """,
            {"base_event_id": base_event["id"]},
        )

    def _fetch_extractions_for_candidates(
        self, *, conn: Connection, candidate_rows: list[RowMapping]
    ) -> dict[int, RowMapping]:
        extraction_ids: set[int] = set()
        for row in candidate_rows:
            candidate_id = row["latest_extraction_id"]
            if isinstance(candidate_id, int) and candidate_id > 0:
                extraction_ids.add(candidate_id)

        if not extraction_ids:
            return {}

        statement = text(
            """
            SELECT id, canonical_payload_json, payload_json
            FROM extractions
            WHERE id IN :extraction_ids
            """
        ).bindparams(bindparam("extraction_ids", expanding=True))
        rows = conn.execute(statement, {"extraction_ids": sorted(extraction_ids)}).mappings().all()
        return {int(row["id"]): row for row in rows}

    def _entity_signature(self, payload: dict[str, Any]) -> set[str]:
        entities = payload.get("entities")
        if not isinstance(entities, dict):
            return set()
        values: set[str] = set()
        for key, prefix in (("countries", "country"), ("orgs", "org"), ("people", "person")):
            items = entities.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, str):
                    cleaned = item.strip().lower()
                    if cleaned:
                        values.add(f"{prefix}:{cleaned}")
        return values

    def _keywords(self, payload: dict[str, Any]) -> set[str]:
        raw_values = payload.get("keywords")
        if not isinstance(raw_values, list):
            return set()
        keywords: set[str] = set()
        for item in raw_values:
            if isinstance(item, str):
                cleaned = item.strip().lower()
                if cleaned:
                    keywords.add(cleaned)
        return keywords

    def _normalized_text(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.lower().strip().split())

    def _summary_ratio(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(a=left, b=right).ratio()

    def _parse_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _validate_readonly_sql(self, *, query: str) -> str:
        trimmed = query.strip()
        if not trimmed:
            raise ServiceError(code="invalid_query", message="Query cannot be empty.")

        if ";" in trimmed:
            if not trimmed.endswith(";") or ";" in trimmed[:-1]:
                raise ServiceError(
                    code="invalid_query",
                    message="Only a single SELECT statement is allowed.",
                )
            trimmed = trimmed[:-1].strip()

        first_token = trimmed.split(maxsplit=1)[0].lower() if trimmed else ""
        if first_token not in {"select", "with"}:
            raise ServiceError(
                code="invalid_query",
                message="Only SELECT (or WITH ... SELECT) statements are allowed.",
            )

        if _MUTATING_SQL_RE.search(trimmed):
            raise ServiceError(
                code="invalid_query",
                message="Mutating SQL keywords are not allowed.",
            )

        if _SELECT_INTO_RE.search(trimmed):
            raise ServiceError(
                code="invalid_query",
                message="SELECT ... INTO statements are not allowed.",
            )

        return trimmed

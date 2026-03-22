from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ...models import Event, EventRelation, EventTag, Extraction
from .contracts import (
    MemoEventTimelineItem,
    MemoSelectionDiagnostics,
    MemoWindow,
    OpportunityMemoInputPack,
    RankedTopicOpportunity,
)
from .driver_selection import select_primary_driver
from .ranking import previous_equivalent_window, rank_topic_opportunities
from .topic_mapping import map_event_to_topic


def _normalize_utc_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def load_event_snapshots(
    db: Session,
    *,
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    start = _normalize_utc_naive(start_time)
    end = _normalize_utc_naive(end_time)

    events = (
        db.query(Event)
        .filter(
            or_(
                and_(Event.event_time.is_not(None), Event.event_time >= start, Event.event_time < end),
                and_(Event.event_time.is_(None), Event.last_updated_at >= start, Event.last_updated_at < end),
            )
        )
        .order_by(Event.event_time.desc().nullslast(), Event.last_updated_at.desc(), Event.id.desc())
        .all()
    )

    if not events:
        return []

    event_ids = [event.id for event in events]
    extraction_ids = [event.latest_extraction_id for event in events if event.latest_extraction_id is not None]

    extraction_by_id: dict[int, Extraction] = {}
    if extraction_ids:
        extraction_rows = db.query(Extraction).filter(Extraction.id.in_(extraction_ids)).all()
        extraction_by_id = {row.id: row for row in extraction_rows}

    tags_by_event: dict[int, list[dict[str, Any]]] = {event_id: [] for event_id in event_ids}
    for row in db.query(EventTag).filter(EventTag.event_id.in_(event_ids)).all():
        tags_by_event.setdefault(row.event_id, []).append(
            {
                "tag_type": row.tag_type,
                "tag_value": row.tag_value,
                "tag_source": row.tag_source,
                "confidence": row.confidence,
            }
        )

    relations_by_event: dict[int, list[dict[str, Any]]] = {event_id: [] for event_id in event_ids}
    for row in db.query(EventRelation).filter(EventRelation.event_id.in_(event_ids)).all():
        relations_by_event.setdefault(row.event_id, []).append(
            {
                "subject_type": row.subject_type,
                "subject_value": row.subject_value,
                "relation_type": row.relation_type,
                "object_type": row.object_type,
                "object_value": row.object_value,
                "relation_source": row.relation_source,
                "inference_level": row.inference_level,
                "confidence": row.confidence,
            }
        )

    snapshots: list[dict[str, Any]] = []
    for event in events:
        extraction_payload: dict[str, Any] = {}
        if event.latest_extraction_id is not None:
            extraction_row = extraction_by_id.get(event.latest_extraction_id)
            if extraction_row is not None:
                payload_candidate = extraction_row.canonical_payload_json or extraction_row.payload_json or {}
                if isinstance(payload_candidate, dict):
                    extraction_payload = payload_candidate

        mapping = map_event_to_topic(
            event_id=event.id,
            tags=tags_by_event.get(event.id, []),
            relations=relations_by_event.get(event.id, []),
            latest_extraction_payload=extraction_payload,
        )

        snapshots.append(
            {
                "id": event.id,
                "event_time": event.event_time,
                "last_updated_at": event.last_updated_at,
                "summary_1_sentence": event.summary_1_sentence or "",
                "impact_score": float(event.impact_score or 0.0),
                "event_identity_fingerprint_v2": event.event_identity_fingerprint_v2,
                "claim_hash": event.claim_hash,
                "tags": tags_by_event.get(event.id, []),
                "relations": relations_by_event.get(event.id, []),
                "latest_extraction_payload": extraction_payload,
                "mapped_topic": mapping.topic,
                "mapping_diagnostics": mapping.diagnostics.model_dump(mode="json"),
            }
        )

    return snapshots


def rank_topic_candidates(
    db: Session,
    *,
    start_time: datetime,
    end_time: datetime,
    topic_universe: list[str],
    limit: int,
    recent_memo_topics: set[str] | None = None,
) -> list[RankedTopicOpportunity]:
    current_events = load_event_snapshots(db, start_time=start_time, end_time=end_time)
    prior_start, prior_end = previous_equivalent_window(start_time=start_time, end_time=end_time)
    prior_events = load_event_snapshots(db, start_time=prior_start, end_time=prior_end)

    return rank_topic_opportunities(
        current_events=current_events,
        prior_events=prior_events,
        start_time=start_time,
        end_time=end_time,
        topic_universe=topic_universe,
        limit=limit,
        recent_memo_topics=recent_memo_topics,
    )


def topic_timeline(
    *,
    snapshots: list[dict[str, Any]],
    topic: str,
    limit: int = 50,
) -> list[MemoEventTimelineItem]:
    topic_events = [row for row in snapshots if row.get("mapped_topic") == topic]
    topic_events.sort(
        key=lambda row: (
            row.get("event_time") or row.get("last_updated_at") or datetime.min,
            int(row.get("id") or 0),
        )
    )

    timeline: list[MemoEventTimelineItem] = []
    for row in topic_events[: max(1, limit)]:
        payload = row.get("latest_extraction_payload")
        entities = payload.get("entities", {}) if isinstance(payload, dict) else {}
        timeline.append(
            MemoEventTimelineItem(
                event_id=int(row.get("id") or 0),
                event_time=row.get("event_time") if isinstance(row.get("event_time"), datetime) else None,
                summary=str(row.get("summary_1_sentence") or "").strip(),
                impact_score=float(row.get("impact_score") or 0.0),
                entities=entities if isinstance(entities, dict) else {},
                tags=[dict(tag) for tag in (row.get("tags") or []) if isinstance(tag, dict)],
                relations=[dict(rel) for rel in (row.get("relations") or []) if isinstance(rel, dict)],
            )
        )

    return timeline


def _supporting_entities(topic_events: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()

    for row in topic_events:
        payload = row.get("latest_extraction_payload")
        if not isinstance(payload, dict):
            continue
        entities = payload.get("entities")
        if not isinstance(entities, dict):
            continue
        for key in ("countries", "orgs", "people", "tickers"):
            values = entities.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, str) and value.strip():
                    counts[(key[:-1] if key.endswith("s") else key, value.strip())] += 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1].lower()))
    return [
        {"type": item[0][0], "value": item[0][1]}
        for item in ranked[: max(1, limit)]
    ]


def _topic_event_stats(
    topic_events: list[dict[str, Any]],
    *,
    start_time: datetime,
    end_time: datetime,
) -> dict[str, float | int]:
    if not topic_events:
        return {
            "event_count": 0,
            "weighted_impact_score": 0.0,
            "average_impact_score": 0.0,
            "max_impact_score": 0.0,
            "recent_event_count": 0,
        }

    total_span_seconds = max(1.0, (end_time - start_time).total_seconds())
    weighted_impact = 0.0
    for row in topic_events:
        ts = row.get("event_time") or row.get("last_updated_at") or start_time
        if not isinstance(ts, datetime):
            ts = start_time
        recency = (ts - start_time).total_seconds() / total_span_seconds
        recency_weight = max(0.5, min(1.0, 0.5 + (0.5 * recency)))
        weighted_impact += float(row.get("impact_score") or 0.0) * recency_weight

    recent_cutoff = end_time - (end_time - start_time) / 3
    recent_event_count = sum(
        1
        for row in topic_events
        if (row.get("event_time") or row.get("last_updated_at") or start_time) >= recent_cutoff
    )
    impact_values = [float(row.get("impact_score") or 0.0) for row in topic_events]
    return {
        "event_count": len(topic_events),
        "weighted_impact_score": round(weighted_impact, 4),
        "average_impact_score": round(sum(impact_values) / float(len(impact_values)), 4),
        "max_impact_score": round(max(impact_values), 4),
        "recent_event_count": int(recent_event_count),
    }


def _driver_evidence_summary(
    *,
    selected_event_ids: list[int],
    selected_driver: Any,
) -> dict[str, Any]:
    if selected_driver is None:
        return {
            "driver_key": None,
            "supporting_event_count": 0,
            "supporting_event_share": 0.0,
            "supporting_event_ids": [],
        }

    supporting_ids = [int(event_id) for event_id in selected_driver.supporting_event_ids]
    denominator = max(1, len(selected_event_ids))
    return {
        "driver_key": selected_driver.driver_key,
        "supporting_event_count": len(supporting_ids),
        "supporting_event_share": round(len(supporting_ids) / float(denominator), 6),
        "supporting_event_ids": supporting_ids,
    }


def _supporting_fact_candidates(
    topic_events: list[dict[str, Any]],
    *,
    max_items: int = 12,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in topic_events:
        event_id = int(row.get("id") or 0)
        if event_id <= 0:
            continue
        summary = str(row.get("summary_1_sentence") or "").strip()
        impact_score = float(row.get("impact_score") or 0.0)
        if summary:
            candidates.append(
                {
                    "fact_key": f"event_{event_id}_summary",
                    "fact_text": f"Event {event_id} impact score {impact_score:.1f}: {summary}",
                    "internal_event_ids": [event_id],
                    "numeric_value": round(impact_score, 2),
                    "unit": "impact_score",
                    "source_hint": "event_layer",
                }
            )

        payload = row.get("latest_extraction_payload")
        if not isinstance(payload, dict):
            continue
        market_stats = payload.get("market_stats")
        if not isinstance(market_stats, list):
            continue
        for stat_idx, stat in enumerate(market_stats):
            if not isinstance(stat, dict):
                continue
            label = str(stat.get("label") or "").strip()
            value = stat.get("value")
            unit = str(stat.get("unit") or "").strip()
            context = str(stat.get("context") or "").strip()
            if not label or not isinstance(value, (int, float)):
                continue
            candidates.append(
                {
                    "fact_key": f"event_{event_id}_market_stat_{stat_idx}",
                    "fact_text": (
                        f"Event {event_id} market stat {label}: {float(value):.3f}"
                        f"{(' ' + unit) if unit else ''}{(' (' + context + ')') if context else ''}."
                    ),
                    "internal_event_ids": [event_id],
                    "numeric_value": float(value),
                    "unit": unit or None,
                    "source_hint": "event_layer",
                }
            )

    candidates.sort(key=lambda row: (row.get("fact_key") or ""))
    return candidates[: max(1, max_items)]


def build_opportunity_memo_input_pack(
    db: Session,
    *,
    start_time: datetime,
    end_time: datetime,
    topic: str,
    topic_score: float,
    selection_reason: str,
    topic_breakdown: dict[str, float],
) -> tuple[OpportunityMemoInputPack, list[dict[str, Any]]]:
    snapshots = load_event_snapshots(db, start_time=start_time, end_time=end_time)
    topic_events = [row for row in snapshots if row.get("mapped_topic") == topic]

    topic_events.sort(
        key=lambda row: (
            -float(row.get("impact_score") or 0.0),
            (row.get("event_time") or row.get("last_updated_at") or datetime.min),
            int(row.get("id") or 0),
        )
    )
    selected_event_ids = [int(row.get("id") or 0) for row in topic_events]

    candidate_drivers, selected_driver = select_primary_driver(
        topic_events=topic_events,
        start_time=start_time,
        end_time=end_time,
    )

    pack = OpportunityMemoInputPack(
        topic=topic,
        window=MemoWindow(start_time=start_time, end_time=end_time),
        selected_event_ids=selected_event_ids,
        event_timeline=topic_timeline(snapshots=snapshots, topic=topic, limit=50),
        candidate_driver_groups=candidate_drivers,
        selected_primary_driver=selected_driver,
        supporting_entities=_supporting_entities(topic_events),
        topic_event_stats=_topic_event_stats(topic_events, start_time=start_time, end_time=end_time),
        driver_evidence_summary=_driver_evidence_summary(
            selected_event_ids=selected_event_ids,
            selected_driver=selected_driver,
        ),
        supporting_fact_candidates=_supporting_fact_candidates(topic_events),
        selection_diagnostics=MemoSelectionDiagnostics(
            topic_score=float(topic_score),
            selection_reason=selection_reason,
            topic_breakdown=topic_breakdown,
        ),
    )
    return pack, topic_events

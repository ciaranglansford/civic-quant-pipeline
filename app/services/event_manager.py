from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Event, EventMessage, Extraction
from ..schemas import ExtractionJson
from .event_windows import get_event_time_window


logger = logging.getLogger("civicquant.events")


def _normalized_values(values: list[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        cleaned = value.strip().lower()
        if cleaned:
            out.add(cleaned)
    return out


def _entity_signature_from_extraction(extraction: ExtractionJson) -> set[str]:
    entities = extraction.entities
    out: set[str] = set()
    out |= {f"country:{v}" for v in _normalized_values(entities.countries)}
    out |= {f"org:{v}" for v in _normalized_values(entities.orgs)}
    out |= {f"person:{v}" for v in _normalized_values(entities.people)}
    return out


def _entity_signature_from_payload(payload: dict) -> set[str]:
    entities = payload.get("entities") if isinstance(payload, dict) else {}
    if not isinstance(entities, dict):
        entities = {}
    out: set[str] = set()
    for key, prefix in (("countries", "country"), ("orgs", "org"), ("people", "person")):
        values = entities.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str):
                cleaned = value.strip().lower()
                if cleaned:
                    out.add(f"{prefix}:{cleaned}")
    return out


def _keywords_from_extraction(extraction: ExtractionJson) -> set[str]:
    return _normalized_values(extraction.keywords)


def _keywords_from_payload(payload: dict) -> set[str]:
    values = payload.get("keywords", []) if isinstance(payload, dict) else []
    if not isinstance(values, list):
        return set()
    out: set[str] = set()
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                out.add(cleaned)
    return out


def _source_from_extraction(extraction: ExtractionJson) -> str:
    return (extraction.source_claimed or "").strip().lower()


def _source_from_payload(payload: dict) -> str:
    value = payload.get("source_claimed") if isinstance(payload, dict) else None
    if isinstance(value, str):
        return value.strip().lower()
    return ""


def _is_contextual_match(
    extraction: ExtractionJson,
    payload: dict,
) -> bool:
    current_entities = _entity_signature_from_extraction(extraction)
    current_keywords = _keywords_from_extraction(extraction)
    current_source = _source_from_extraction(extraction)

    candidate_entities = _entity_signature_from_payload(payload)
    candidate_keywords = _keywords_from_payload(payload)
    candidate_source = _source_from_payload(payload)

    entity_overlap = len(current_entities & candidate_entities)
    keyword_overlap = len(current_keywords & candidate_keywords)
    same_source = bool(current_source and candidate_source and current_source == candidate_source)

    if entity_overlap >= 2:
        return True
    if same_source and keyword_overlap >= 2:
        return True
    if entity_overlap >= 1 and keyword_overlap >= 2:
        return True
    return False


def _find_contextual_candidate_event(
    db: Session,
    *,
    extraction: ExtractionJson,
    start: datetime,
    end: datetime,
) -> Event | None:
    candidates = (
        db.query(Event)
        .filter(
            Event.topic == extraction.topic,
            Event.event_time.isnot(None),
            Event.event_time >= start,
            Event.event_time <= end,
        )
        .order_by(Event.last_updated_at.desc())
        .all()
    )

    latest_ids = [candidate.latest_extraction_id for candidate in candidates if candidate.latest_extraction_id is not None]
    if not latest_ids:
        return None

    extraction_rows = db.query(Extraction).filter(Extraction.id.in_(latest_ids)).all()
    by_id = {row.id: row for row in extraction_rows}

    for candidate in candidates:
        if candidate.latest_extraction_id is None:
            continue
        latest = by_id.get(candidate.latest_extraction_id)
        if latest is None:
            continue
        payload = latest.canonical_payload_json or latest.payload_json or {}
        if not isinstance(payload, dict):
            continue
        if _is_contextual_match(extraction, payload):
            logger.info(
                "event_soft_match event_id=%s extraction_topic=%s extraction_fingerprint=%s",
                candidate.id,
                extraction.topic,
                extraction.event_fingerprint,
            )
            return candidate

    return None


def find_candidate_event(
    db: Session,
    *,
    extraction: ExtractionJson,
) -> Event | None:
    event_time = extraction.event_time or datetime.utcnow()
    window = get_event_time_window(extraction.topic, extraction.is_breaking)
    start = event_time - window
    end = event_time + window

    strict_candidate = None
    if extraction.event_fingerprint:
        strict_candidate = (
            db.query(Event)
            .filter(
                Event.event_fingerprint == extraction.event_fingerprint,
                Event.event_time.isnot(None),
                Event.event_time >= start,
                Event.event_time <= end,
            )
            .order_by(Event.last_updated_at.desc())
            .first()
        )
        if strict_candidate is not None:
            return strict_candidate

    return _find_contextual_candidate_event(db, extraction=extraction, start=start, end=end)


def update_event_from_extraction(event: Event, extraction: ExtractionJson, latest_extraction_id: int | None) -> dict[str, tuple[object | None, object | None]]:
    changes: dict[str, tuple[object | None, object | None]] = {}

    def _set(name: str, new_value: object | None) -> None:
        old_value = getattr(event, name)
        if old_value != new_value:
            setattr(event, name, new_value)
            changes[name] = (old_value, new_value)

    # Prefer non-null fields and higher impact score.
    if extraction.summary_1_sentence and extraction.summary_1_sentence != (event.summary_1_sentence or ""):
        _set("summary_1_sentence", extraction.summary_1_sentence)

    if event.impact_score is None or extraction.impact_score > float(event.impact_score):
        _set("impact_score", float(extraction.impact_score))

    if event.topic is None and extraction.topic:
        _set("topic", extraction.topic)

    if extraction.is_breaking and not bool(event.is_breaking):
        _set("is_breaking", True)
        _set("breaking_window", extraction.breaking_window)

    if event.event_time is None and extraction.event_time is not None:
        _set("event_time", extraction.event_time)

    if latest_extraction_id is not None:
        _set("latest_extraction_id", latest_extraction_id)

    _set("last_updated_at", datetime.utcnow())
    # Reset channel publish flags when event is updated so future digest windows
    # can republish materially updated events per destination.
    _set("is_published_telegram", False)
    _set("is_published_twitter", False)
    return changes


def upsert_event(
    db: Session,
    extraction: ExtractionJson,
    raw_message_id: int,
    latest_extraction_id: int | None = None,
) -> tuple[int, str]:
    event_time = extraction.event_time or datetime.utcnow()
    candidate = find_candidate_event(db, extraction=extraction)

    if candidate is None:
        stored_fingerprint = extraction.event_fingerprint or f"soft:{raw_message_id}"
        event = Event(
            event_fingerprint=stored_fingerprint,
            topic=extraction.topic,
            summary_1_sentence=extraction.summary_1_sentence,
            impact_score=float(extraction.impact_score),
            is_breaking=bool(extraction.is_breaking),
            breaking_window=extraction.breaking_window,
            event_time=event_time,
            last_updated_at=datetime.utcnow(),
            latest_extraction_id=latest_extraction_id,
        )
        db.add(event)
        db.flush()
        db.add(EventMessage(event_id=event.id, raw_message_id=raw_message_id))
        logger.info(
            "event_create raw_message_id=%s event_id=%s fingerprint=%s",
            raw_message_id,
            event.id,
            stored_fingerprint,
        )
        return event.id, "create"

    changes = update_event_from_extraction(candidate, extraction, latest_extraction_id)
    db.add(EventMessage(event_id=candidate.id, raw_message_id=raw_message_id))
    logger.info(
        "event_update raw_message_id=%s event_id=%s fingerprint=%s changes=%s",
        raw_message_id,
        candidate.id,
        extraction.event_fingerprint,
        ",".join(sorted(changes.keys())) if changes else "none",
    )
    return candidate.id, "update"


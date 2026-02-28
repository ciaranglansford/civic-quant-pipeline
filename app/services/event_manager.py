from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Event, EventMessage
from ..schemas import ExtractionJson
from .event_windows import get_event_time_window


logger = logging.getLogger("civicquant.events")


def find_candidate_event(
    db: Session,
    *,
    extraction: ExtractionJson,
) -> Event | None:
    event_time = extraction.event_time or datetime.utcnow()
    window = get_event_time_window(extraction.topic, extraction.is_breaking)
    start = event_time - window
    end = event_time + window
    return (
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
        event = Event(
            event_fingerprint=extraction.event_fingerprint,
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
            extraction.event_fingerprint,
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


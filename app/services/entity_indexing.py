from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import EntityMention
from ..schemas import ExtractionJson


def _upsert_entity_mention(
    db: Session,
    *,
    raw_message_id: int,
    event_id: int | None,
    entity_type: str,
    entity_value: str,
    topic: str,
    is_breaking: bool,
    event_time: datetime | None,
) -> None:
    existing = (
        db.query(EntityMention)
        .filter_by(
            raw_message_id=raw_message_id,
            entity_type=entity_type,
            entity_value=entity_value,
        )
        .one_or_none()
    )
    if existing is not None:
        if event_id is not None:
            existing.event_id = event_id
        return

    db.add(
        EntityMention(
            raw_message_id=raw_message_id,
            event_id=event_id,
            entity_type=entity_type,
            entity_value=entity_value,
            topic=topic,
            is_breaking=is_breaking,
            event_time=event_time,
        )
    )
    db.flush()


def index_entities_for_extraction(
    db: Session,
    *,
    raw_message_id: int,
    event_id: int | None,
    extraction: ExtractionJson,
) -> None:
    for country in extraction.entities.countries:
        _upsert_entity_mention(
            db,
            raw_message_id=raw_message_id,
            event_id=event_id,
            entity_type="country",
            entity_value=country,
            topic=extraction.topic,
            is_breaking=extraction.is_breaking,
            event_time=extraction.event_time,
        )

    for org in extraction.entities.orgs:
        _upsert_entity_mention(
            db,
            raw_message_id=raw_message_id,
            event_id=event_id,
            entity_type="org",
            entity_value=org,
            topic=extraction.topic,
            is_breaking=extraction.is_breaking,
            event_time=extraction.event_time,
        )

    for person in extraction.entities.people:
        _upsert_entity_mention(
            db,
            raw_message_id=raw_message_id,
            event_id=event_id,
            entity_type="person",
            entity_value=person,
            topic=extraction.topic,
            is_breaking=extraction.is_breaking,
            event_time=extraction.event_time,
        )

    for ticker in extraction.entities.tickers:
        _upsert_entity_mention(
            db,
            raw_message_id=raw_message_id,
            event_id=event_id,
            entity_type="ticker",
            entity_value=ticker,
            topic=extraction.topic,
            is_breaking=extraction.is_breaking,
            event_time=extraction.event_time,
        )


def query_entity_mentions(
    db: Session,
    *,
    entity_type: str,
    entity_value: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[EntityMention]:
    q = db.query(EntityMention).filter(
        EntityMention.entity_type == entity_type,
        EntityMention.entity_value == entity_value,
    )
    if start_time is not None:
        q = q.filter(EntityMention.event_time.is_not(None), EntityMention.event_time >= start_time)
    if end_time is not None:
        q = q.filter(EntityMention.event_time.is_not(None), EntityMention.event_time <= end_time)
    return q.order_by(EntityMention.event_time.desc().nullslast(), EntityMention.id.desc()).all()

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from ...models import EnrichmentCandidate, Event, EventRelation, EventTag
from ...structured_contracts import (
    normalize_directionality,
    normalize_relation_entity_type,
    normalize_relation_type,
    normalize_relation_value,
    normalize_tag_family,
    normalize_tag_value,
)


def _normalize_time(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _event_base_query(
    db: Session,
    *,
    start_time: datetime,
    end_time: datetime,
    min_impact: float | None,
) -> object:
    query = db.query(Event).filter(
        Event.event_time.is_not(None),
        Event.event_time >= _normalize_time(start_time),
        Event.event_time <= _normalize_time(end_time),
    )
    if min_impact is not None:
        query = query.filter(Event.impact_score.is_not(None), Event.impact_score >= float(min_impact))
    return query


def _apply_directionality_filter(query: object, *, directionality: str | None) -> object:
    if directionality is None:
        return query
    normalized = normalize_directionality(directionality)
    if normalized is None:
        raise ValueError("invalid directionality")

    directionality_tag = aliased(EventTag)
    return query.join(
        directionality_tag,
        directionality_tag.event_id == Event.id,
    ).filter(
        directionality_tag.tag_type == "directionality",
        func.lower(directionality_tag.tag_value) == normalized.lower(),
    )


def query_events_by_tag(
    db: Session,
    *,
    tag_type: str,
    tag_value: str,
    start_time: datetime,
    end_time: datetime,
    min_impact: float | None = None,
    directionality: str | None = None,
    limit: int = 100,
) -> list[Event]:
    normalized_tag_type = normalize_tag_family(tag_type)
    normalized_tag_value = normalize_tag_value(tag_value)
    if normalized_tag_type is None or normalized_tag_value is None:
        raise ValueError("invalid tag filter")

    query = _event_base_query(
        db,
        start_time=start_time,
        end_time=end_time,
        min_impact=min_impact,
    ).join(EventTag, EventTag.event_id == Event.id).filter(
        EventTag.tag_type == normalized_tag_type,
        func.lower(EventTag.tag_value) == normalized_tag_value.lower(),
    )
    query = _apply_directionality_filter(query, directionality=directionality)
    return (
        query.distinct()
        .order_by(
            Event.impact_score.desc().nullslast(),
            Event.event_time.desc().nullslast(),
            Event.id.desc(),
        )
        .limit(limit)
        .all()
    )


def query_events_by_relation(
    db: Session,
    *,
    relation_type: str,
    start_time: datetime,
    end_time: datetime,
    min_impact: float | None = None,
    directionality: str | None = None,
    subject_type: str | None = None,
    subject_value: str | None = None,
    object_type: str | None = None,
    object_value: str | None = None,
    limit: int = 100,
) -> list[Event]:
    normalized_relation_type = normalize_relation_type(relation_type)
    if normalized_relation_type is None:
        raise ValueError("invalid relation_type")

    query = _event_base_query(
        db,
        start_time=start_time,
        end_time=end_time,
        min_impact=min_impact,
    ).join(EventRelation, EventRelation.event_id == Event.id).filter(
        EventRelation.relation_type == normalized_relation_type,
    )

    if subject_type is not None:
        normalized_subject_type = normalize_relation_entity_type(subject_type)
        if normalized_subject_type is None:
            raise ValueError("invalid subject_type")
        query = query.filter(EventRelation.subject_type == normalized_subject_type)
    if subject_value is not None:
        normalized_subject_value = normalize_relation_value(subject_value)
        if normalized_subject_value is None:
            raise ValueError("invalid subject_value")
        query = query.filter(func.lower(EventRelation.subject_value) == normalized_subject_value.lower())
    if object_type is not None:
        normalized_object_type = normalize_relation_entity_type(object_type)
        if normalized_object_type is None:
            raise ValueError("invalid object_type")
        query = query.filter(EventRelation.object_type == normalized_object_type)
    if object_value is not None:
        normalized_object_value = normalize_relation_value(object_value)
        if normalized_object_value is None:
            raise ValueError("invalid object_value")
        query = query.filter(func.lower(EventRelation.object_value) == normalized_object_value.lower())

    query = _apply_directionality_filter(query, directionality=directionality)
    return (
        query.distinct()
        .order_by(
            Event.impact_score.desc().nullslast(),
            Event.event_time.desc().nullslast(),
            Event.id.desc(),
        )
        .limit(limit)
        .all()
    )


def serialize_query_results(db: Session, *, events: list[Event]) -> list[dict[str, object]]:
    event_ids = [event.id for event in events]
    if not event_ids:
        return []

    directionality_rows = (
        db.query(EventTag.event_id, EventTag.tag_value)
        .filter(
            EventTag.event_id.in_(event_ids),
            EventTag.tag_type == "directionality",
        )
        .all()
    )
    directionality_by_event = {event_id: tag_value for event_id, tag_value in directionality_rows}

    route_rows = (
        db.query(EnrichmentCandidate.event_id, EnrichmentCandidate.enrichment_route)
        .filter(EnrichmentCandidate.event_id.in_(event_ids))
        .all()
    )
    route_by_event = {event_id: route for event_id, route in route_rows}

    items: list[dict[str, object]] = []
    for event in events:
        items.append(
            {
                "id": event.id,
                "topic": event.topic,
                "summary": event.summary_1_sentence,
                "event_time": event.event_time.isoformat() if event.event_time else None,
                "impact_score": float(event.impact_score or 0.0),
                "directionality": directionality_by_event.get(event.id),
                "enrichment_route": route_by_event.get(event.id),
            }
        )
    return items

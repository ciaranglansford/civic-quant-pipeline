from __future__ import annotations

from sqlalchemy.orm import Session

from ...models import EventRelation, EventTag
from ...schemas import ExtractionJson


def _dedupe_tag_rows(extraction: ExtractionJson) -> list[EventTag]:
    rows: list[EventTag] = []
    seen: set[tuple[str, str, str]] = set()
    for tag in extraction.tags:
        key = (tag.tag_type, tag.tag_value.lower(), tag.tag_source)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            EventTag(
                tag_type=tag.tag_type,
                tag_value=tag.tag_value,
                tag_source=tag.tag_source,
                confidence=tag.confidence,
            )
        )
    return rows


def _dedupe_relation_rows(extraction: ExtractionJson) -> list[EventRelation]:
    rows: list[EventRelation] = []
    seen: set[tuple[str, str, str, str, str, str, int]] = set()
    for relation in extraction.relations:
        inference_level = int(relation.inference_level or 0)
        key = (
            relation.subject_type,
            relation.subject_value.lower(),
            relation.relation_type,
            relation.object_type,
            relation.object_value.lower(),
            relation.relation_source,
            inference_level,
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            EventRelation(
                subject_type=relation.subject_type,
                subject_value=relation.subject_value,
                relation_type=relation.relation_type,
                object_type=relation.object_type,
                object_value=relation.object_value,
                relation_source=relation.relation_source,
                inference_level=inference_level,
                confidence=relation.confidence,
            )
        )
    return rows


def sync_event_tags_and_relations(
    db: Session,
    *,
    event_id: int,
    extraction: ExtractionJson,
) -> None:
    """Replace an event's normalized tag/relation rows from canonical extraction output."""
    db.query(EventTag).filter(EventTag.event_id == event_id).delete(synchronize_session=False)
    db.query(EventRelation).filter(EventRelation.event_id == event_id).delete(synchronize_session=False)

    for row in _dedupe_tag_rows(extraction):
        row.event_id = event_id
        db.add(row)
    for row in _dedupe_relation_rows(extraction):
        row.event_id = event_id
        db.add(row)
    db.flush()

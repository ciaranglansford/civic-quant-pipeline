from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


from ..models import EventMessage, MessageProcessingState, RawMessage, RoutingDecision
from ..schemas import RoutingDecisionData, TelegramIngestPayload


logger = logging.getLogger("civicquant.pipeline")


def _get_existing_raw(db: Session, source_channel_id: str, telegram_message_id: str) -> RawMessage | None:
    return (
        db.query(RawMessage)
        .filter(
            RawMessage.source_channel_id == source_channel_id,
            RawMessage.telegram_message_id == telegram_message_id,
        )
        .one_or_none()
    )


def _get_event_id_for_raw(db: Session, raw_message_id: int) -> int | None:
    link = db.query(EventMessage).filter(EventMessage.raw_message_id == raw_message_id).first()
    return link.event_id if link else None




def store_routing_decision(db: Session, raw_message_id: int, decision: RoutingDecisionData) -> int:
    existing = db.query(RoutingDecision).filter(RoutingDecision.raw_message_id == raw_message_id).one_or_none()
    if existing is not None:
        return existing.id

    row = RoutingDecision(
        raw_message_id=raw_message_id,
        store_to=decision.store_to,
        publish_priority=decision.publish_priority,
        requires_evidence=decision.requires_evidence,
        event_action=decision.event_action,
        triage_action=decision.triage_action,
        triage_rules=decision.triage_rules,
        flags=decision.flags,
    )
    db.add(row)
    db.flush()
    return row.id

def process_ingest_payload(
    db: Session,
    payload: TelegramIngestPayload,
    normalized_text: str,
) -> dict[str, object]:
    existing = _get_existing_raw(db, payload.source_channel_id, payload.telegram_message_id)
    if existing is not None:
        event_id = _get_event_id_for_raw(db, existing.id)
        return {
            "status": "duplicate",
            "raw_message_id": existing.id,
            "event_id": event_id,
            "event_action": None,
        }

    raw = RawMessage(
        source_channel_id=payload.source_channel_id,
        source_channel_name=payload.source_channel_name,
        telegram_message_id=payload.telegram_message_id,
        message_timestamp_utc=payload.message_timestamp_utc.replace(tzinfo=None),
        raw_text=payload.raw_text,
        raw_entities=payload.raw_entities_if_available,
        forwarded_from=payload.forwarded_from_if_available,
        normalized_text=normalized_text,
    )

    try:
        db.add(raw)
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = _get_existing_raw(db, payload.source_channel_id, payload.telegram_message_id)
        if existing is None:
            raise
        event_id = _get_event_id_for_raw(db, existing.id)
        return {
            "status": "duplicate",
            "raw_message_id": existing.id,
            "event_id": event_id,
            "event_action": None,
        }

    db.add(MessageProcessingState(raw_message_id=raw.id, status="pending", attempt_count=0))
    db.flush()

    logger.info("ingest_stored raw_message_id=%s phase2_state=pending", raw.id)

    return {
        "status": "created",
        "raw_message_id": raw.id,
        "event_id": None,
        "event_action": None,
    }

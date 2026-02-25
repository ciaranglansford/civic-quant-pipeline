from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import EventMessage, Extraction, RawMessage, RoutingDecision
from ..schemas import ExtractionJson, RoutingDecisionData, TelegramIngestPayload
from .event_manager import upsert_event
from .extraction_agent import ExtractionAgent
from .routing_engine import route_extraction


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


def store_extraction(db: Session, raw_message_id: int, extraction: ExtractionJson, model_name: str) -> int:
    existing = db.query(Extraction).filter(Extraction.raw_message_id == raw_message_id).one_or_none()
    if existing is not None:
        return existing.id

    row = Extraction(
        raw_message_id=raw_message_id,
        model_name=model_name,
        extraction_json=extraction.model_dump(mode="json"),
    )
    db.add(row)
    db.flush()
    return row.id


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
        flags=decision.flags,
    )
    db.add(row)
    db.flush()
    return row.id


def process_ingest_payload(
    db: Session,
    payload: TelegramIngestPayload,
    normalized_text: str,
    extractor: ExtractionAgent | None = None,
) -> dict[str, object]:
    """
    End-to-end ingest processing for Phase 1:
    - Insert RawMessage (idempotent)
    - Extract (stub)
    - Route (rules)
    - Event upsert (fingerprint/time-window)
    - Persist Extraction and RoutingDecision
    """
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

    extractor = extractor or ExtractionAgent()
    extraction = extractor.extract(
        normalized_text=normalized_text,
        message_time=payload.message_timestamp_utc,
        source_channel_name=payload.source_channel_name,
    )

    extraction_id = store_extraction(db, raw.id, extraction, extractor.model_name)

    decision = route_extraction(extraction)
    store_routing_decision(db, raw.id, decision)

    event_id = None
    event_action = None
    if decision.event_action != "ignore":
        event_id, event_action = upsert_event(
            db=db,
            extraction=extraction,
            raw_message_id=raw.id,
            latest_extraction_id=extraction_id,
        )

    logger.info(
        "pipeline_done raw_message_id=%s event_id=%s event_action=%s fingerprint=%s priority=%s",
        raw.id,
        event_id,
        event_action,
        extraction.event_fingerprint,
        decision.publish_priority,
    )

    return {
        "status": "created",
        "raw_message_id": raw.id,
        "event_id": event_id,
        "event_action": event_action,
    }


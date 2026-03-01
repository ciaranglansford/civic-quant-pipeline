from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import Extraction, MessageProcessingState, ProcessingLock, RawMessage
from ..schemas import ExtractionJson
from .canonicalization import canonicalize_extraction
from .entity_indexing import index_entities_for_extraction
from .event_manager import find_candidate_event, upsert_event
from .extraction_llm_client import OpenAiExtractionClient, ProviderError
from .extraction_validation import ExtractionValidationError, parse_and_validate_extraction
from .prompt_templates import render_extraction_prompt
from .routing_engine import route_extraction
from .triage_engine import (
    CandidateEventContext,
    TriageContext,
    compute_triage_action,
    impact_band,
    entity_signature,
)
from .ingest_pipeline import store_routing_decision


logger = logging.getLogger("civicquant.phase2")
OPENAI_EXTRACTOR_NAME = "extract-and-score-openai-v1"
EXTRACTION_SCHEMA_VERSION = 1


@dataclass
class RunSummary:
    processing_run_id: str
    selected: int = 0
    processed: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0


def ensure_processing_state(db: Session, raw_message_id: int) -> MessageProcessingState:
    state = db.query(MessageProcessingState).filter_by(raw_message_id=raw_message_id).one_or_none()
    if state:
        return state
    state = MessageProcessingState(raw_message_id=raw_message_id, status="pending", attempt_count=0)
    db.add(state)
    db.flush()
    return state


def get_eligible_messages_for_extraction(db: Session, *, batch_size: int) -> list[RawMessage]:
    now = datetime.utcnow()
    return (
        db.query(RawMessage)
        .outerjoin(MessageProcessingState, MessageProcessingState.raw_message_id == RawMessage.id)
        .filter(
            or_(
                MessageProcessingState.id.is_(None),
                MessageProcessingState.status.in_(["pending", "failed"]),
                (MessageProcessingState.status == "in_progress")
                & (MessageProcessingState.lease_expires_at.is_not(None))
                & (MessageProcessingState.lease_expires_at <= now),
            )
        )
        .order_by(RawMessage.message_timestamp_utc.asc(), RawMessage.id.asc())
        .limit(batch_size)
        .all()
    )


def _acquire_lock(db: Session, *, run_id: str, lock_seconds: int) -> bool:
    now = datetime.utcnow()
    lock = db.query(ProcessingLock).filter_by(lock_name="phase2_extraction").one_or_none()
    if lock and lock.locked_until > now:
        return False
    until = now + timedelta(seconds=lock_seconds)
    if lock is None:
        db.add(ProcessingLock(lock_name="phase2_extraction", locked_until=until, owner_run_id=run_id))
    else:
        lock.locked_until = until
        lock.owner_run_id = run_id
    db.flush()
    return True


def _release_lock(db: Session, run_id: str) -> None:
    lock = db.query(ProcessingLock).filter_by(lock_name="phase2_extraction").one_or_none()
    if lock and lock.owner_run_id == run_id:
        lock.locked_until = datetime.utcnow()
        db.flush()


def _payload_for_extraction_row(row: Extraction) -> dict:
    payload = row.canonical_payload_json or row.payload_json or {}
    return payload if isinstance(payload, dict) else {}


def _entities_from_payload(payload: dict) -> set[str]:
    entities = payload.get("entities") if isinstance(payload, dict) else {}
    if not isinstance(entities, dict):
        entities = {}
    out: set[str] = set()
    for key in ("countries", "orgs", "people"):
        values = entities.get(key, [])
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    out.add(f"{key[:-1]}:{value.strip().lower()}")
    return out


def _summary_tags_from_text(summary: str) -> set[str]:
    normalized = summary.lower()
    tags: set[str] = set()
    if any(token in normalized for token in ("condemn", "concern", "urge", "calls for", "unacceptable", "warn", "respond")):
        tags.add("reaction")
    if any(token in normalized for token in ("strike", "attack", "launched", "killed", "injured", "casualties", "missile", "troops", "explosion")):
        tags.add("operational")
    return tags


def _source_class_from_payload(payload: dict) -> str:
    source = str(payload.get("source_claimed") or "").lower()
    summary = str(payload.get("summary_1_sentence") or "").lower()
    combined = f"{source} {summary}"
    if any(token in combined for token in ("police", "ministry", "official", "military", "agency", "spokesperson", "according to")):
        return "authority"
    if any(token in combined for token in ("commentary", "analyst", "opinion", "urges", "condemns", "concerned")):
        return "commentary"
    return "unknown"


def _candidate_event_context(db: Session, existing_event) -> CandidateEventContext | None:
    if existing_event is None or existing_event.latest_extraction_id is None:
        return None
    latest = db.query(Extraction).filter_by(id=existing_event.latest_extraction_id).one_or_none()
    if latest is None:
        return None
    payload = _payload_for_extraction_row(latest)
    summary = str(payload.get("summary_1_sentence") or "")
    impact_val = latest.impact_score if latest.impact_score is not None else float(payload.get("impact_score") or 0.0)
    return CandidateEventContext(
        impact_band=impact_band(float(impact_val)),
        entities=_entities_from_payload(payload),
        summary_tags=_summary_tags_from_text(summary),
        source_class=_source_class_from_payload(payload),
    )


def _recent_related_rows(
    db: Session,
    *,
    extraction_model: ExtractionJson,
    raw_message_id: int,
    now_time: datetime,
) -> list[Extraction]:
    start = now_time - timedelta(minutes=15)
    end = now_time
    return (
        db.query(Extraction)
        .filter(
            Extraction.raw_message_id != raw_message_id,
            Extraction.topic == extraction_model.topic,
            Extraction.created_at >= start,
            Extraction.created_at <= end,
        )
        .order_by(Extraction.created_at.asc())
        .all()
    )


def _burst_low_delta_prior_count(
    extraction_model: ExtractionJson,
    recent_rows: list[Extraction],
) -> tuple[bool, int]:
    current_entities = entity_signature(extraction_model)
    current_band_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}[impact_band(extraction_model.impact_score)]
    prior_entity_union: set[str] = set()
    qualifying = 0
    soft_related_match = False

    for row in recent_rows:
        payload = _payload_for_extraction_row(row)
        row_fp = str(payload.get("event_fingerprint") or row.event_fingerprint or "")
        row_entities = _entities_from_payload(payload)
        overlap = len(current_entities & row_entities)
        related = (row_fp and row_fp == extraction_model.event_fingerprint) or overlap >= 2
        if not related:
            continue
        soft_related_match = True
        prior_entity_union |= row_entities
        row_impact = row.impact_score if row.impact_score is not None else float(payload.get("impact_score") or 0.0)
        row_band_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}[impact_band(float(row_impact))]
        impact_not_increasing = current_band_rank <= row_band_rank
        no_new_entities = len(current_entities - prior_entity_union) == 0
        if impact_not_increasing and no_new_entities:
            qualifying += 1

    return soft_related_match, qualifying


def process_phase2_batch(db: Session, settings: Settings | None = None) -> RunSummary:
    settings = settings or get_settings()
    run_id = str(uuid.uuid4())
    summary = RunSummary(processing_run_id=run_id)

    if not _acquire_lock(db, run_id=run_id, lock_seconds=settings.phase2_scheduler_lock_seconds):
        logger.info("phase2_lock_busy processing_run_id=%s", run_id)
        return summary

    try:
        if not settings.phase2_extraction_enabled:
            raise ValueError("PHASE2_EXTRACTION_ENABLED must be true for phase2 extraction job")
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when PHASE2_EXTRACTION_ENABLED=true")

        logger.info("Using extractor: %s", OPENAI_EXTRACTOR_NAME)

        client = OpenAiExtractionClient(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )

        eligible = get_eligible_messages_for_extraction(db, batch_size=settings.phase2_batch_size)
        summary.selected = len(eligible)
        for raw in eligible:
            state = ensure_processing_state(db, raw.id)
            if state.status == "completed":
                summary.skipped += 1
                continue

            state.status = "in_progress"
            state.processing_run_id = run_id
            state.last_attempted_at = datetime.utcnow()
            state.attempt_count += 1
            state.lease_expires_at = datetime.utcnow() + timedelta(seconds=settings.phase2_lease_seconds)
            state.last_error = None
            db.flush()

            try:
                prompt = render_extraction_prompt(
                    normalized_text=raw.normalized_text,
                    message_time=raw.message_timestamp_utc,
                    source_channel_name=raw.source_channel_name,
                )
                llm_response = client.extract(prompt.prompt_text)
                parsed = parse_and_validate_extraction(llm_response.raw_text)
                canonicalized_model, canonicalization_rules = canonicalize_extraction(parsed)
                extraction_model = ExtractionJson.model_validate(canonicalized_model.model_dump(mode="json"))
                canonical_payload = extraction_model.model_dump(mode="json")
                raw_payload = parsed

                extraction = db.query(Extraction).filter_by(raw_message_id=raw.id).one_or_none()
                if extraction is None:
                    extraction = Extraction(
                        raw_message_id=raw.id,
                        extractor_name=OPENAI_EXTRACTOR_NAME,
                        schema_version=EXTRACTION_SCHEMA_VERSION,
                        payload_json=raw_payload,
                    )
                    db.add(extraction)
                extraction.extractor_name = OPENAI_EXTRACTOR_NAME
                extraction.schema_version = EXTRACTION_SCHEMA_VERSION
                extraction.model_name = llm_response.model_name
                extraction.event_time = extraction_model.event_time
                extraction.topic = extraction_model.topic
                extraction.impact_score = float(extraction_model.impact_score)
                extraction.confidence = float(extraction_model.confidence)
                extraction.sentiment = extraction_model.sentiment
                extraction.is_breaking = bool(extraction_model.is_breaking)
                extraction.breaking_window = extraction_model.breaking_window
                extraction.event_fingerprint = extraction_model.event_fingerprint
                extraction.prompt_version = prompt.prompt_version
                extraction.processing_run_id = run_id
                extraction.llm_raw_response = llm_response.raw_text
                extraction.validated_at = datetime.utcnow()
                extraction.payload_json = raw_payload
                extraction.canonical_payload_json = canonical_payload
                extraction.metadata_json = {
                    "used_openai": llm_response.used_openai,
                    "openai_model": llm_response.model_name,
                    "openai_response_id": llm_response.openai_response_id,
                    "latency_ms": llm_response.latency_ms,
                    "retries": llm_response.retries,
                    "fallback_reason": None,
                    "canonicalization_rules": canonicalization_rules,
                }
                db.flush()

                existing_event = find_candidate_event(db, extraction=extraction_model)
                candidate_context = _candidate_event_context(db, existing_event)
                now_time = raw.message_timestamp_utc or datetime.utcnow()
                recent = _recent_related_rows(
                    db,
                    extraction_model=extraction_model,
                    raw_message_id=raw.id,
                    now_time=now_time,
                )
                soft_related, burst_prior_count = _burst_low_delta_prior_count(extraction_model, recent)
                triage = compute_triage_action(
                    extraction_model,
                    context=TriageContext(
                        existing_event_id=(existing_event.id if existing_event is not None else None),
                        candidate_event=candidate_context,
                        soft_related_match=soft_related,
                        burst_low_delta_prior_count=burst_prior_count,
                    ),
                )
                decision = route_extraction(
                    extraction_model,
                    triage_action=triage.triage_action,
                    triage_rules=triage.reason_codes,
                )
                if triage.triage_action == "archive":
                    decision.event_action = "ignore"
                elif triage.triage_action == "update" and existing_event is not None:
                    decision.event_action = "update"
                store_routing_decision(db, raw.id, decision)
                event_id: int | None = None
                if decision.event_action != "ignore":
                    event_id, _ = upsert_event(
                        db=db,
                        extraction=extraction_model,
                        raw_message_id=raw.id,
                        latest_extraction_id=extraction.id,
                    )
                index_entities_for_extraction(
                    db,
                    raw_message_id=raw.id,
                    event_id=event_id,
                    extraction=extraction_model,
                )

                state.status = "completed"
                state.completed_at = datetime.utcnow()
                state.lease_expires_at = None
                summary.completed += 1
            except ExtractionValidationError as e:
                state.status = "failed"
                state.last_error = f"validation_error:{e}"
                logger.warning(
                    "phase2_extraction_failed raw_message_id=%s reason=%s fallback_reason=%s",
                    raw.id,
                    "validation_error",
                    str(e),
                )
                summary.failed += 1
            except ProviderError as e:
                state.status = "failed"
                state.last_error = f"provider_error:{e}"
                logger.warning(
                    "phase2_extraction_failed raw_message_id=%s reason=%s fallback_reason=%s",
                    raw.id,
                    "provider_error",
                    str(e),
                )
                summary.failed += 1
            except Exception as e:  # noqa: BLE001
                state.status = "failed"
                state.last_error = f"persistence_error:{type(e).__name__}"
                logger.exception(
                    "phase2_extraction_failed raw_message_id=%s reason=%s fallback_reason=%s",
                    raw.id,
                    "persistence_error",
                    type(e).__name__,
                )
                summary.failed += 1
            finally:
                summary.processed += 1
                db.flush()

        logger.info(
            "phase2_run_done processing_run_id=%s selected=%s processed=%s completed=%s failed=%s skipped=%s",
            run_id,
            summary.selected,
            summary.processed,
            summary.completed,
            summary.failed,
            summary.skipped,
        )
        return summary
    finally:
        _release_lock(db, run_id)

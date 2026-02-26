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
from .event_manager import upsert_event
from .extraction_llm_client import OpenAiExtractionClient, ProviderError
from .extraction_validation import ExtractionValidationError, parse_and_validate_extraction
from .prompt_templates import render_extraction_prompt
from .routing_engine import route_extraction
from .ingest_pipeline import store_routing_decision


logger = logging.getLogger("civicquant.phase2")


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


def process_phase2_batch(db: Session, settings: Settings | None = None) -> RunSummary:
    settings = settings or get_settings()
    run_id = str(uuid.uuid4())
    summary = RunSummary(processing_run_id=run_id)

    if not _acquire_lock(db, run_id=run_id, lock_seconds=settings.phase2_scheduler_lock_seconds):
        logger.info("phase2_lock_busy processing_run_id=%s", run_id)
        return summary

    try:
        if settings.phase2_extraction_enabled and not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when PHASE2_EXTRACTION_ENABLED=true")

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
                extraction_model = ExtractionJson.model_validate(parsed)

                extraction = db.query(Extraction).filter_by(raw_message_id=raw.id).one_or_none()
                if extraction is None:
                    extraction = Extraction(raw_message_id=raw.id, extraction_json=parsed)
                    db.add(extraction)
                extraction.model_name = llm_response.model_name
                extraction.prompt_version = prompt.prompt_version
                extraction.processing_run_id = run_id
                extraction.llm_raw_response = llm_response.raw_text
                extraction.validated_at = datetime.utcnow()
                extraction.extraction_json = parsed
                db.flush()

                decision = route_extraction(extraction_model)
                store_routing_decision(db, raw.id, decision)
                if decision.event_action != "ignore":
                    upsert_event(
                        db=db,
                        extraction=extraction_model,
                        raw_message_id=raw.id,
                        latest_extraction_id=extraction.id,
                    )

                state.status = "completed"
                state.completed_at = datetime.utcnow()
                state.lease_expires_at = None
                summary.completed += 1
            except ExtractionValidationError as e:
                state.status = "failed"
                state.last_error = f"validation_error:{e}"
                summary.failed += 1
            except ProviderError as e:
                state.status = "failed"
                state.last_error = f"provider_error:{e}"
                summary.failed += 1
            except Exception as e:  # noqa: BLE001
                state.status = "failed"
                state.last_error = f"persistence_error:{type(e).__name__}"
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

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..contexts.entities.entity_indexing import index_entities_for_extraction
from ..contexts.enrichment.enrichment_selection import select_and_store_enrichment_candidate
from ..contexts.events.event_manager import EventUpsertResult, upsert_event
from ..contexts.events.structured_persistence import sync_event_tags_and_relations
from ..contexts.extraction.canonicalization import CANONICALIZER_VERSION
from ..contexts.extraction.extraction_llm_client import OpenAiExtractionClient, ProviderError
from ..contexts.extraction.extraction_validation import ExtractionValidationError
from ..contexts.themes.evidence import persist_theme_matches_for_event
from ..contexts.extraction.processing import (
    OPENAI_EXTRACTOR_NAME,
    materialize_extraction_for_raw_message,
)
from ..contexts.triage.decisioning import (
    apply_identity_conflict_override,
    compute_routing_decision,
)
from ..contexts.triage.impact_scoring import distribution_metrics
from ..contexts.triage.routing_decisions import upsert_routing_decision
from ..models import Event, MessageProcessingState, ProcessingLock, RawMessage


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


def process_phase2_batch(
    db: Session,
    settings: Settings | None = None,
    *,
    force_reprocess: bool = False,
) -> RunSummary:
    settings = settings or get_settings()
    effective_force_reprocess = bool(force_reprocess or settings.phase2_force_reprocess)
    run_id = str(uuid.uuid4())
    summary = RunSummary(processing_run_id=run_id)
    calibrated_scores: list[float] = []

    if not _acquire_lock(db, run_id=run_id, lock_seconds=settings.phase2_scheduler_lock_seconds):
        logger.info("phase2_lock_busy processing_run_id=%s", run_id)
        return summary

    try:
        if not settings.phase2_extraction_enabled:
            raise ValueError("PHASE2_EXTRACTION_ENABLED must be true for phase2 extraction job")
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when PHASE2_EXTRACTION_ENABLED=true")

        logger.info(
            "Using extractor: %s force_reprocess=%s canonicalizer_version=%s",
            OPENAI_EXTRACTOR_NAME,
            effective_force_reprocess,
            CANONICALIZER_VERSION,
        )

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
                processed = materialize_extraction_for_raw_message(
                    db,
                    raw=raw,
                    run_id=run_id,
                    settings=settings,
                    client=client,
                    force_reprocess=effective_force_reprocess,
                )
                routing = compute_routing_decision(
                    db,
                    raw_message_id=raw.id,
                    extraction_model=processed.extraction_model,
                )
                decision = routing.decision

                event_id: int | None = None
                upsert_result: EventUpsertResult | None = None
                if decision.event_action != "ignore":
                    upsert_result = upsert_event(
                        db=db,
                        extraction=processed.extraction_model,
                        raw_message_id=raw.id,
                        latest_extraction_id=processed.extraction_row.id,
                        canonical_payload_hash=processed.canonical_payload_hash,
                        claim_hash=processed.claim_hash,
                        action_class=processed.action_class,
                        time_bucket=processed.time_bucket,
                    )
                    event_id = upsert_result.event_id

                apply_identity_conflict_override(decision, upsert_result)
                upsert_routing_decision(db, raw.id, decision)

                if event_id is not None:
                    sync_event_tags_and_relations(
                        db,
                        event_id=event_id,
                        extraction=processed.extraction_model,
                    )
                    event_row = db.query(Event).filter_by(id=event_id).one_or_none()
                    if event_row is not None:
                        persist_theme_matches_for_event(
                            db,
                            event=event_row,
                            extraction=processed.extraction_row,
                        )
                    try:
                        select_and_store_enrichment_candidate(
                            db,
                            event_id=event_id,
                            extraction=processed.extraction_model,
                            calibration=processed.calibration,
                            triage_action=decision.triage_action,
                            triage_rules=decision.triage_rules,
                            existing_event_id=routing.existing_event_id,
                            now=routing.evaluated_at,
                        )
                    except Exception as enrichment_exc:  # noqa: BLE001
                        logger.warning(
                            "enrichment_selection_failed raw_message_id=%s event_id=%s reason=%s",
                            raw.id,
                            event_id,
                            type(enrichment_exc).__name__,
                        )

                index_entities_for_extraction(
                    db,
                    raw_message_id=raw.id,
                    event_id=event_id,
                    extraction=processed.extraction_model,
                )

                calibrated_scores.append(float(processed.calibration.calibrated_score))
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

        if calibrated_scores:
            metrics = distribution_metrics(calibrated_scores)
            logger.info(
                "phase2_score_distribution processing_run_id=%s count=%s p95=%s p99=%s pct_gt_40=%s pct_gt_60=%s pct_gte_80=%s",
                run_id,
                int(metrics["count"]),
                metrics["p95"],
                metrics["p99"],
                metrics["pct_gt_40"],
                metrics["pct_gt_60"],
                metrics["pct_gte_80"],
            )

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

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..contexts.enrichment.deep_enrichment import run_deep_enrichment_batch
from ..models import ProcessingLock


@dataclass(frozen=True)
class DeepEnrichmentRunSummary:
    run_id: str
    selected: int
    processed: int
    created: int
    skipped_existing: int
    lock_busy: bool = False


def _acquire_lock(db: Session, *, run_id: str, lock_seconds: int) -> bool:
    now = datetime.utcnow()
    lock = db.query(ProcessingLock).filter_by(lock_name="deep_enrichment").one_or_none()
    if lock is not None and lock.locked_until > now:
        return False
    until = now + timedelta(seconds=lock_seconds)
    if lock is None:
        db.add(ProcessingLock(lock_name="deep_enrichment", locked_until=until, owner_run_id=run_id))
    else:
        lock.locked_until = until
        lock.owner_run_id = run_id
    db.flush()
    return True


def _release_lock(db: Session, *, run_id: str) -> None:
    lock = db.query(ProcessingLock).filter_by(lock_name="deep_enrichment").one_or_none()
    if lock is not None and lock.owner_run_id == run_id:
        lock.locked_until = datetime.utcnow()
        db.flush()


def process_deep_enrichment_batch(
    db: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
) -> DeepEnrichmentRunSummary:
    settings = settings or get_settings()
    run_id = str(uuid.uuid4())
    batch_size = int(limit or settings.deep_enrichment_batch_size)

    if not settings.deep_enrichment_enabled:
        return DeepEnrichmentRunSummary(
            run_id=run_id,
            selected=0,
            processed=0,
            created=0,
            skipped_existing=0,
            lock_busy=False,
        )

    if not _acquire_lock(db, run_id=run_id, lock_seconds=settings.phase2_scheduler_lock_seconds):
        return DeepEnrichmentRunSummary(
            run_id=run_id,
            selected=0,
            processed=0,
            created=0,
            skipped_existing=0,
            lock_busy=True,
        )

    try:
        result = run_deep_enrichment_batch(db, limit=batch_size)
        return DeepEnrichmentRunSummary(
            run_id=run_id,
            selected=result.selected,
            processed=result.processed,
            created=result.created,
            skipped_existing=result.skipped_existing,
            lock_busy=False,
        )
    finally:
        _release_lock(db, run_id=run_id)

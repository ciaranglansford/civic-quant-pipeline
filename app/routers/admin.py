from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services.phase2_processing import process_phase2_batch


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/process/phase2-extractions")
def trigger_phase2_extractions(
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if not settings.phase2_admin_token or x_admin_token != settings.phase2_admin_token:
        raise HTTPException(status_code=401, detail="unauthorized")

    summary = process_phase2_batch(db=db, settings=settings)
    db.commit()
    return {
        "processing_run_id": summary.processing_run_id,
        "selected": summary.selected,
        "processed": summary.processed,
        "completed": summary.completed,
        "failed": summary.failed,
        "skipped": summary.skipped,
    }

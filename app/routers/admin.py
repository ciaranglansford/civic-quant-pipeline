from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import get_settings
from ..contexts.events.structured_query import (
    query_events_by_relation,
    query_events_by_tag,
    serialize_query_results,
)
from ..db import get_db
from ..workflows.phase2_pipeline import process_phase2_batch


router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin_token(x_admin_token: str | None) -> None:
    settings = get_settings()
    if not settings.phase2_admin_token or x_admin_token != settings.phase2_admin_token:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/process/phase2-extractions")
def trigger_phase2_extractions(
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None),
    force_reprocess: bool = Query(default=False),
) -> dict[str, object]:
    settings = get_settings()
    _require_admin_token(x_admin_token)
    summary = process_phase2_batch(db=db, settings=settings, force_reprocess=force_reprocess)
    db.commit()
    return {
        "processing_run_id": summary.processing_run_id,
        "selected": summary.selected,
        "processed": summary.processed,
        "completed": summary.completed,
        "failed": summary.failed,
        "skipped": summary.skipped,
    }


@router.get("/query/events/by-tag")
def query_events_by_tag_endpoint(
    tag_type: str = Query(...),
    tag_value: str = Query(...),
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    min_impact: float | None = Query(default=None),
    directionality: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _require_admin_token(x_admin_token)
    try:
        rows = query_events_by_tag(
            db,
            tag_type=tag_type,
            tag_value=tag_value,
            start_time=start_time,
            end_time=end_time,
            min_impact=min_impact,
            directionality=directionality,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": serialize_query_results(db, events=rows), "count": len(rows)}


@router.get("/query/events/by-relation")
def query_events_by_relation_endpoint(
    relation_type: str = Query(...),
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    min_impact: float | None = Query(default=None),
    directionality: str | None = Query(default=None),
    subject_type: str | None = Query(default=None),
    subject_value: str | None = Query(default=None),
    object_type: str | None = Query(default=None),
    object_value: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _require_admin_token(x_admin_token)
    try:
        rows = query_events_by_relation(
            db,
            relation_type=relation_type,
            start_time=start_time,
            end_time=end_time,
            min_impact=min_impact,
            directionality=directionality,
            subject_type=subject_type,
            subject_value=subject_value,
            object_type=object_type,
            object_value=object_value,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": serialize_query_results(db, events=rows), "count": len(rows)}


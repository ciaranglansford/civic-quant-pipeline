from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..logging_utils import new_request_id
from ..schemas import IngestResponse, TelegramIngestPayload
from ..services.normalization import normalize_message_text
from ..services.ingest_pipeline import process_ingest_payload


logger = logging.getLogger("civicquant.ingest")
router = APIRouter(tags=["ingest"])


@router.post("/ingest/telegram", response_model=IngestResponse)
def ingest_telegram(
    payload: TelegramIngestPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> IngestResponse:
    request_id = request.headers.get("x-request-id") or new_request_id()
    normalized = normalize_message_text(payload.raw_text)
    try:
        result = process_ingest_payload(db=db, payload=payload, normalized_text=normalized)
        db.commit()
        logger.info(
            "ingest_ok request_id=%s source_channel_id=%s telegram_message_id=%s raw_message_id=%s status=%s event_id=%s",
            request_id,
            payload.source_channel_id,
            payload.telegram_message_id,
            result["raw_message_id"],
            result["status"],
            result.get("event_id"),
        )
        return IngestResponse(
            status=result["status"],  # type: ignore[arg-type]
            raw_message_id=int(result["raw_message_id"]),
            event_id=(int(result["event_id"]) if result.get("event_id") is not None else None),
            event_action=result.get("event_action"),  # type: ignore[arg-type]
        )
    except Exception as e:
        db.rollback()
        logger.exception(
            "ingest_failed request_id=%s source_channel_id=%s telegram_message_id=%s error=%s",
            request_id,
            payload.source_channel_id,
            payload.telegram_message_id,
            type(e).__name__,
        )
        raise HTTPException(status_code=500, detail="ingest failed")


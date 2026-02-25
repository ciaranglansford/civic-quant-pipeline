from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import PublishedPost
from .digest_builder import build_digest
from .digest_query import get_events_for_digest
from .telegram_publisher import send_digest_to_vip


logger = logging.getLogger("civicquant.digest")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_recent_duplicate(db: Session, destination: str, content_hash: str, within_hours: int) -> bool:
    cutoff = datetime.utcnow() - timedelta(hours=within_hours)
    existing = (
        db.query(PublishedPost)
        .filter(
            PublishedPost.destination == destination,
            PublishedPost.content_hash == content_hash,
            PublishedPost.published_at >= cutoff,
        )
        .first()
    )
    return existing is not None


def run_digest(db: Session, window_hours: int) -> dict[str, object]:
    events = get_events_for_digest(db, hours=window_hours)
    text = build_digest(events, window_hours=window_hours)
    content_hash = _content_hash(text)
    destination = "vip_telegram"

    if has_recent_duplicate(db, destination=destination, content_hash=content_hash, within_hours=window_hours):
        logger.info("digest_skip_duplicate destination=%s hash=%s", destination, content_hash)
        return {"status": "skipped_duplicate", "content_hash": content_hash, "event_ids": [e.id for e in events]}

    send_digest_to_vip(text)

    row = PublishedPost(
        event_id=None,
        destination=destination,
        published_at=datetime.utcnow(),
        content=text,
        content_hash=content_hash,
    )
    db.add(row)
    db.flush()
    logger.info("digest_published destination=%s hash=%s published_post_id=%s", destination, content_hash, row.id)
    return {"status": "published", "content_hash": content_hash, "published_post_id": row.id, "event_ids": [e.id for e in events]}


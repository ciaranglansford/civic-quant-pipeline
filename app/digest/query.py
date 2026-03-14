from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..models import Event


def _destination_unpublished_filter(destination: str):
    if destination == "vip_telegram":
        return or_(Event.is_published_telegram.is_(False), Event.is_published_telegram.is_(None))
    if destination == "x":
        return or_(Event.is_published_twitter.is_(False), Event.is_published_twitter.is_(None))
    return None


def get_events_for_window(
    db: Session,
    window_start_utc: datetime,
    window_end_utc: datetime,
    *,
    min_impact_exclusive: float | None = None,
    destination: str | None = None,
) -> list[Event]:
    q = db.query(Event).filter(
        Event.last_updated_at >= window_start_utc,
        Event.last_updated_at < window_end_utc,
    )
    if min_impact_exclusive is not None:
        q = q.filter(Event.impact_score.isnot(None), Event.impact_score > min_impact_exclusive)

    if destination is not None:
        unpublished_filter = _destination_unpublished_filter(destination)
        if unpublished_filter is not None:
            q = q.filter(unpublished_filter)

    return q.order_by(Event.last_updated_at.desc(), Event.id.asc()).all()


def get_events_for_digest_hours(
    db: Session, hours: int, *, now_utc: datetime | None = None
) -> list[Event]:
    end_utc = (now_utc or datetime.utcnow()).replace(microsecond=0)
    start_utc = end_utc - timedelta(hours=hours)
    return get_events_for_window(db, window_start_utc=start_utc, window_end_utc=end_utc)

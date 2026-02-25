from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Event


def get_events_for_digest(db: Session, hours: int) -> list[Event]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return (
        db.query(Event)
        .filter(
            (Event.last_updated_at >= cutoff)
            | ((Event.event_time.isnot(None)) & (Event.event_time >= cutoff))
        )
        .order_by(Event.last_updated_at.desc())
        .all()
    )


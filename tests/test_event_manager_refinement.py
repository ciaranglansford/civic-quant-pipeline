from __future__ import annotations

import os
from datetime import datetime, timedelta

from app.schemas import ExtractionEntities, ExtractionJson


def _extraction(*, summary: str, impact: float, event_time: datetime) -> ExtractionJson:
    return ExtractionJson(
        topic="war_security",
        entities=ExtractionEntities(countries=["United States"], orgs=["AP"], people=[], tickers=[]),
        affected_countries_first_order=["United States"],
        market_stats=[],
        sentiment="negative",
        confidence=0.8,
        impact_score=impact,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        source_claimed="AP",
        summary_1_sentence=summary,
        keywords=["conflict"],
        event_fingerprint="war_security|2025-01-01|United States|ap|||" + summary.lower().replace(" ", "_"),
    )


def test_event_upsert_links_repetitive_and_updates_summary():
    db_path = "./test_civicquant_events.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, init_db
    from app.models import Event, EventMessage
    from app.services.event_manager import upsert_event

    init_db()
    now = datetime.utcnow()

    with SessionLocal() as db:
        base = _extraction(summary="Officials report strike.", impact=40.0, event_time=now)
        follow_up = _extraction(
            summary="Officials report strike; details disputed.",
            impact=65.0,
            event_time=now + timedelta(minutes=10),
        )
        # keep same fingerprint to simulate paraphrase/contradictory observation.
        follow_up.event_fingerprint = base.event_fingerprint

        e1, a1 = upsert_event(db, base, raw_message_id=1001, latest_extraction_id=None)
        e2, a2 = upsert_event(db, follow_up, raw_message_id=1002, latest_extraction_id=None)
        db.commit()

        assert e1 == e2
        assert a1 == "create"
        assert a2 == "update"

        event = db.query(Event).filter_by(id=e1).one()
        assert event.summary_1_sentence == "Officials report strike; details disputed."
        assert float(event.impact_score or 0.0) == 65.0
        links = db.query(EventMessage).filter_by(event_id=e1).all()
        assert len(links) == 2


def test_event_upsert_does_not_soft_merge_different_fingerprints():
    db_path = "./test_civicquant_events_soft.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, init_db
    from app.models import Event
    from app.services.event_manager import upsert_event

    init_db()
    now = datetime.utcnow()

    with SessionLocal() as db:
        first = _extraction(summary="Soft merge guard case one.", impact=60.0, event_time=now)
        second = _extraction(summary="Soft merge guard case two.", impact=62.0, event_time=now + timedelta(minutes=5))
        second.event_fingerprint = "war_security|2025-01-01|United States|ap|||different"

        e1, a1 = upsert_event(db, first, raw_message_id=2001, latest_extraction_id=None)
        e2, a2 = upsert_event(db, second, raw_message_id=2002, latest_extraction_id=None)
        db.commit()

        assert a1 == "create"
        assert a2 == "create"
        assert e1 != e2
        fingerprints = {
            row.event_fingerprint
            for row in db.query(Event).filter(Event.id.in_([e1, e2])).all()
        }
        assert len(fingerprints) == 2

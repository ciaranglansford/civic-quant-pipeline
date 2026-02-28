from __future__ import annotations

import os
from datetime import datetime, timedelta

from app.schemas import ExtractionEntities, ExtractionJson


def _extraction(event_time: datetime) -> ExtractionJson:
    return ExtractionJson(
        topic="geopolitics",
        entities=ExtractionEntities(
            countries=["United States"],
            orgs=["AP"],
            people=["John Doe"],
            tickers=["EUR"],
        ),
        affected_countries_first_order=["United States"],
        market_stats=[],
        sentiment="neutral",
        confidence=0.7,
        impact_score=60.0,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        source_claimed="AP",
        summary_1_sentence="Reported claim.",
        keywords=["reported"],
        event_fingerprint="f",
    )


def test_entity_indexing_insert_dedup_and_time_window_query():
    db_path = "./test_civicquant_entities.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"

    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import SessionLocal, init_db
    from app.models import EntityMention
    from app.services.entity_indexing import index_entities_for_extraction, query_entity_mentions

    init_db()
    now = datetime.utcnow()
    extraction = _extraction(now)

    with SessionLocal() as db:
        index_entities_for_extraction(db, raw_message_id=2001, event_id=301, extraction=extraction)
        index_entities_for_extraction(db, raw_message_id=2001, event_id=301, extraction=extraction)
        db.commit()

        all_rows = db.query(EntityMention).filter_by(raw_message_id=2001).all()
        assert len(all_rows) == 4

        in_window = query_entity_mentions(
            db,
            entity_type="country",
            entity_value="United States",
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(minutes=5),
        )
        assert len(in_window) == 1

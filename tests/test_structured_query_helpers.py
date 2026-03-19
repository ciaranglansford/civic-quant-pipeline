from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.events.structured_persistence import sync_event_tags_and_relations
from app.contexts.events.structured_query import query_events_by_relation, query_events_by_tag
from app.db import Base
from app.models import Event
from app.schemas import ExtractionEntities, ExtractionJson


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def _extraction(*, event_time: datetime, impact: float, directionality: str, country: str) -> ExtractionJson:
    return ExtractionJson(
        topic="commodities",
        event_type="production",
        directionality=directionality,
        entities=ExtractionEntities(countries=[country], orgs=["NIOC"], people=[], tickers=[]),
        affected_countries_first_order=[country],
        market_stats=[],
        tags=[
            {"tag_type": "countries", "tag_value": country, "tag_source": "observed", "confidence": 0.9},
            {"tag_type": "commodities", "tag_value": "Oil", "tag_source": "observed", "confidence": 0.9},
            {"tag_type": "directionality", "tag_value": directionality, "tag_source": "observed", "confidence": 0.9},
        ],
        relations=[
            {
                "subject_type": "country",
                "subject_value": country,
                "relation_type": "restricts_export_of",
                "object_type": "commodity",
                "object_value": "Oil",
                "relation_source": "observed",
                "inference_level": 0,
                "confidence": 0.8,
            }
        ],
        impact_inputs={
            "severity_cues": ["restriction"],
            "economic_relevance_cues": ["oil"],
            "propagation_potential_cues": ["shipping"],
            "specificity_cues": ["export"],
            "novelty_cues": ["new"],
            "strategic_tag_hits": ["supply_risk"],
        },
        sentiment="negative",
        confidence=0.8,
        impact_score=impact,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        source_claimed="Reuters",
        summary_1_sentence=f"{country} restricts oil exports.",
        keywords=["oil", "export restriction"],
        event_core="restriction",
        event_fingerprint=f"fp-{country}-{event_time.isoformat()}",
    )


def test_query_helpers_support_tag_relation_timeframe_and_filters():
    SessionLocal, engine = _session_factory()
    now = datetime.utcnow().replace(microsecond=0)

    try:
        with SessionLocal() as db:
            event_a = Event(
                event_fingerprint="structured-q-1",
                topic="commodities",
                summary_1_sentence="Iran restricts exports.",
                impact_score=82.0,
                is_breaking=True,
                breaking_window="1h",
                event_time=now - timedelta(hours=1),
                last_updated_at=now - timedelta(hours=1),
            )
            event_b = Event(
                event_fingerprint="structured-q-2",
                topic="commodities",
                summary_1_sentence="Saudi Arabia easing restrictions.",
                impact_score=58.0,
                is_breaking=False,
                breaking_window="none",
                event_time=now - timedelta(hours=2),
                last_updated_at=now - timedelta(hours=2),
            )
            db.add_all([event_a, event_b])
            db.flush()

            sync_event_tags_and_relations(
                db,
                event_id=event_a.id,
                extraction=_extraction(
                    event_time=event_a.event_time,
                    impact=82.0,
                    directionality="stress",
                    country="Iran",
                ),
            )
            sync_event_tags_and_relations(
                db,
                event_id=event_b.id,
                extraction=_extraction(
                    event_time=event_b.event_time,
                    impact=58.0,
                    directionality="easing",
                    country="Saudi Arabia",
                ),
            )
            db.commit()

            start = now - timedelta(hours=6)
            end = now

            by_tag = query_events_by_tag(
                db,
                tag_type="commodities",
                tag_value="Oil",
                start_time=start,
                end_time=end,
                min_impact=60.0,
                directionality="stress",
            )
            assert [event.id for event in by_tag] == [event_a.id]

            by_relation = query_events_by_relation(
                db,
                relation_type="restricts_export_of",
                start_time=start,
                end_time=end,
                min_impact=50.0,
                directionality="easing",
            )
            assert [event.id for event in by_relation] == [event_b.id]

            ordered = query_events_by_tag(
                db,
                tag_type="commodities",
                tag_value="Oil",
                start_time=start,
                end_time=end,
            )
            assert [event.id for event in ordered] == [event_a.id, event_b.id]
    finally:
        engine.dispose()

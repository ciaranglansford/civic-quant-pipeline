from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.events.structured_persistence import sync_event_tags_and_relations
from app.db import Base
from app.models import Event, EventRelation, EventTag
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


def _extraction(*, summary: str, tags: list[dict[str, object]], relations: list[dict[str, object]]) -> ExtractionJson:
    return ExtractionJson(
        topic="commodities",
        event_type="production",
        directionality="stress",
        entities=ExtractionEntities(
            countries=["Iran"],
            orgs=["NIOC"],
            people=[],
            tickers=[],
        ),
        affected_countries_first_order=["Iran"],
        market_stats=[],
        tags=tags,
        relations=relations,
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
        impact_score=70.0,
        is_breaking=True,
        breaking_window="1h",
        event_time=datetime.utcnow(),
        source_claimed="Reuters",
        summary_1_sentence=summary,
        keywords=["oil", "export restriction"],
        event_core="restriction",
        event_fingerprint="fp",
    )


def test_sync_persists_and_dedupes_tags_relations():
    SessionLocal, engine = _session_factory()

    try:
        with SessionLocal() as db:
            event = Event(
                event_fingerprint="event-sync-1",
                topic="commodities",
                summary_1_sentence="Initial",
                impact_score=70.0,
                is_breaking=True,
                breaking_window="1h",
                event_time=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            db.add(event)
            db.flush()

            extraction = _extraction(
                summary="Restriction update",
                tags=[
                    {"tag_type": "countries", "tag_value": "Iran", "tag_source": "observed", "confidence": 0.9},
                    {"tag_type": "countries", "tag_value": "Iran", "tag_source": "observed", "confidence": 0.9},
                    {"tag_type": "strategic", "tag_value": "supply_risk", "tag_source": "inferred", "confidence": 0.6},
                ],
                relations=[
                    {
                        "subject_type": "country",
                        "subject_value": "Iran",
                        "relation_type": "restricts_export_of",
                        "object_type": "commodity",
                        "object_value": "Oil",
                        "relation_source": "observed",
                        "inference_level": 0,
                        "confidence": 0.8,
                    },
                    {
                        "subject_type": "country",
                        "subject_value": "Iran",
                        "relation_type": "restricts_export_of",
                        "object_type": "commodity",
                        "object_value": "Oil",
                        "relation_source": "observed",
                        "inference_level": 0,
                        "confidence": 0.8,
                    },
                ],
            )
            sync_event_tags_and_relations(db, event_id=event.id, extraction=extraction)
            sync_event_tags_and_relations(db, event_id=event.id, extraction=extraction)
            db.commit()

            tags = db.query(EventTag).filter_by(event_id=event.id).all()
            relations = db.query(EventRelation).filter_by(event_id=event.id).all()
            assert len(tags) == 2
            assert len(relations) == 1
    finally:
        engine.dispose()


def test_sync_replaces_stale_rows_when_event_updates():
    SessionLocal, engine = _session_factory()

    try:
        with SessionLocal() as db:
            event = Event(
                event_fingerprint="event-sync-2",
                topic="commodities",
                summary_1_sentence="Initial",
                impact_score=65.0,
                is_breaking=True,
                breaking_window="1h",
                event_time=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            db.add(event)
            db.flush()

            first = _extraction(
                summary="First",
                tags=[
                    {"tag_type": "countries", "tag_value": "Iran", "tag_source": "observed", "confidence": 0.9},
                    {"tag_type": "commodities", "tag_value": "Oil", "tag_source": "observed", "confidence": 0.9},
                ],
                relations=[
                    {
                        "subject_type": "country",
                        "subject_value": "Iran",
                        "relation_type": "restricts_export_of",
                        "object_type": "commodity",
                        "object_value": "Oil",
                        "relation_source": "observed",
                        "inference_level": 0,
                        "confidence": 0.8,
                    }
                ],
            )
            second = _extraction(
                summary="Second",
                tags=[
                    {"tag_type": "countries", "tag_value": "Saudi Arabia", "tag_source": "observed", "confidence": 0.9}
                ],
                relations=[],
            )

            sync_event_tags_and_relations(db, event_id=event.id, extraction=first)
            db.flush()
            sync_event_tags_and_relations(db, event_id=event.id, extraction=second)
            db.commit()

            tags = db.query(EventTag).filter_by(event_id=event.id).order_by(EventTag.tag_type.asc()).all()
            relations = db.query(EventRelation).filter_by(event_id=event.id).all()
            assert [(tag.tag_type, tag.tag_value) for tag in tags] == [("countries", "Saudi Arabia")]
            assert relations == []
    finally:
        engine.dispose()

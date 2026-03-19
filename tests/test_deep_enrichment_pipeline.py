from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base
from app.models import EnrichmentCandidate, Event, EventDeepEnrichment, Extraction, RawMessage
from app.workflows.deep_enrichment_pipeline import process_deep_enrichment_batch


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def test_deep_enrichment_pipeline_processes_only_shortlisted_and_is_idempotent():
    SessionLocal, engine = _session_factory()
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        deep_enrichment_enabled=True,
        deep_enrichment_batch_size=10,
    )
    now = datetime.utcnow()

    try:
        with SessionLocal() as db:
            raw = RawMessage(
                source_channel_id="test",
                source_channel_name="feed",
                telegram_message_id="deep-enrich-1",
                message_timestamp_utc=now,
                raw_text="Iran restricts exports.",
                normalized_text="iran restricts exports",
            )
            db.add(raw)
            db.flush()

            extraction = Extraction(
                raw_message_id=raw.id,
                extractor_name="extract-and-score-openai-v1",
                schema_version=1,
                topic="commodities",
                event_time=now,
                impact_score=86.0,
                confidence=0.8,
                sentiment="negative",
                is_breaking=True,
                breaking_window="1h",
                event_fingerprint="fp-deep",
                payload_json={},
                canonical_payload_json={
                    "summary_1_sentence": "Iran restricts oil exports.",
                    "directionality": "stress",
                    "tags": [
                        {"tag_type": "strategic", "tag_value": "supply_risk"},
                        {"tag_type": "commodities", "tag_value": "Oil"},
                    ],
                    "relations": [
                        {
                            "subject_type": "country",
                            "subject_value": "Iran",
                            "relation_type": "restricts_export_of",
                            "object_type": "commodity",
                            "object_value": "Oil",
                            "relation_source": "observed",
                            "inference_level": 0,
                        }
                    ],
                },
                metadata_json={},
            )
            db.add(extraction)
            db.flush()

            shortlisted = Event(
                event_fingerprint="event-shortlisted",
                topic="commodities",
                summary_1_sentence="Shortlisted event",
                impact_score=86.0,
                is_breaking=True,
                breaking_window="1h",
                event_time=now,
                last_updated_at=now,
                latest_extraction_id=extraction.id,
            )
            other = Event(
                event_fingerprint="event-other",
                topic="commodities",
                summary_1_sentence="Not shortlisted",
                impact_score=55.0,
                is_breaking=False,
                breaking_window="none",
                event_time=now,
                last_updated_at=now,
            )
            db.add_all([shortlisted, other])
            db.flush()

            db.add(
                EnrichmentCandidate(
                    event_id=shortlisted.id,
                    selected=True,
                    enrichment_route="deep_enrich",
                    triage_action="promote",
                    reason_codes=["enrichment:selected"],
                    novelty_state="novel",
                    novelty_cluster_key="cluster-1",
                    calibrated_score=86.0,
                    raw_llm_score=70.0,
                    score_band="top",
                    shock_flags=["major_commodity_disruption"],
                    score_breakdown={"transmission_criteria_met": True},
                    scored_at=now,
                )
            )
            db.add(
                EnrichmentCandidate(
                    event_id=other.id,
                    selected=False,
                    enrichment_route="index_only",
                    triage_action="monitor",
                    reason_codes=["enrichment:not_eligible_route"],
                    novelty_state="novel",
                    novelty_cluster_key="cluster-2",
                    calibrated_score=55.0,
                    raw_llm_score=50.0,
                    score_band="medium",
                    shock_flags=[],
                    score_breakdown={},
                    scored_at=now,
                )
            )
            db.commit()

            first = process_deep_enrichment_batch(db, settings=settings)
            db.commit()
            assert first.selected == 1
            assert first.created == 1
            rows = db.query(EventDeepEnrichment).all()
            assert len(rows) == 1
            assert rows[0].event_id == shortlisted.id

            second = process_deep_enrichment_batch(db, settings=settings)
            db.commit()
            assert second.selected == 1
            assert second.created == 0
            assert second.skipped_existing == 1
            rows_after = db.query(EventDeepEnrichment).all()
            assert len(rows_after) == 1
    finally:
        engine.dispose()

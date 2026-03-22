from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.contexts.opportunity_memo.contracts import (
    ExternalEvidencePack,
    ExternalEvidenceSource,
    OpportunityMemoStructuredArtifact,
)
from app.db import Base
from app.models import (
    Event,
    EventRelation,
    EventTag,
    Extraction,
    OpportunityMemoArtifact,
    OpportunityMemoDelivery,
    OpportunityMemoExternalSource,
    OpportunityMemoInputEvent,
    OpportunityMemoRun,
    RawMessage,
)
from app.workflows import opportunity_memo_pipeline
from app.workflows.opportunity_memo_pipeline import run_opportunity_memo


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def _seed_natural_gas_events(db, *, now: datetime) -> None:
    for idx, hours_back in enumerate([4, 3, 2], start=1):
        event_time = now - timedelta(hours=hours_back)
        raw = RawMessage(
            source_channel_id="seed",
            source_channel_name="seed",
            telegram_message_id=f"m-{idx}",
            message_timestamp_utc=event_time,
            raw_text="noise from raw layer should not drive memo",
            normalized_text="noise from raw layer should not drive memo",
        )
        db.add(raw)
        db.flush()

        payload = {
            "topic": "commodities",
            "summary_1_sentence": "Natural gas disruption supports higher risk premium.",
            "keywords": ["natural gas", "disruption", "supply", "pricing"],
            "entities": {
                "countries": ["Qatar"],
                "orgs": ["Terminal Operator"],
                "people": [],
                "tickers": ["TTF"],
            },
            "market_stats": [{"label": "volatility", "value": 1.0, "unit": "%", "context": "up"}],
        }
        extraction = Extraction(
            raw_message_id=raw.id,
            extractor_name="extract-and-score-openai-v1",
            schema_version=1,
            event_time=event_time,
            topic="commodities",
            impact_score=82.0 - idx,
            confidence=0.9,
            sentiment="negative",
            is_breaking=True,
            breaking_window="1h",
            event_fingerprint=f"e-{idx}",
            event_identity_fingerprint_v2=f"e-{idx}",
            payload_json=payload,
            canonical_payload_json=payload,
            metadata_json={"impact_scoring": {"calibrated_score": 82.0 - idx}},
            claim_hash=f"claim-{idx}",
        )
        db.add(extraction)
        db.flush()

        event = Event(
            event_fingerprint=f"event-{idx}",
            event_identity_fingerprint_v2=f"event-{idx}",
            topic="commodities",
            summary_1_sentence="Natural gas disruption supports higher risk premium.",
            impact_score=82.0 - idx,
            is_breaking=True,
            breaking_window="1h",
            event_time=event_time,
            last_updated_at=event_time,
            latest_extraction_id=extraction.id,
            claim_hash=f"claim-{idx}",
        )
        db.add(event)
        db.flush()

        db.add(
            EventTag(
                event_id=event.id,
                tag_type="commodities",
                tag_value="Natural Gas",
                tag_source="observed",
                confidence=0.9,
            )
        )
        db.add(
            EventRelation(
                event_id=event.id,
                subject_type="country",
                subject_value="Qatar",
                relation_type="curtails",
                object_type="commodity",
                object_value="Natural Gas",
                relation_source="observed",
                inference_level=0,
                confidence=0.8,
            )
        )
    db.flush()


class _FakeResearchProvider:
    name = "fake_research"

    def retrieve(self, *, input_pack, plan, settings):  # noqa: ANN001, ARG002
        now = datetime.utcnow()
        return ExternalEvidencePack(
            topic=input_pack.topic,
            provider_name=self.name,
            sources=[
                ExternalEvidenceSource(
                    source_id="src_01",
                    source_type="web",
                    title="Source 1",
                    publisher="Pub1",
                    retrieved_at=now,
                    query="q1",
                    summary="Source one summary",
                    claim_support_tags=["confirm"],
                    url="https://example.com/1",
                ),
                ExternalEvidenceSource(
                    source_id="src_02",
                    source_type="web",
                    title="Source 2",
                    publisher="Pub2",
                    retrieved_at=now,
                    query="q2",
                    summary="Source two summary",
                    claim_support_tags=["context"],
                    url="https://example.com/2",
                ),
                ExternalEvidenceSource(
                    source_id="src_03",
                    source_type="web",
                    title="Source 3",
                    publisher="Pub3",
                    retrieved_at=now,
                    query="q3",
                    summary="Source three summary",
                    claim_support_tags=["risk"],
                    url="https://example.com/3",
                ),
            ],
            retrieval_diagnostics={"fake": True},
        )


class _FakeWriter:
    name = "fake_writer"

    def write(self, *, input_pack, external_evidence, settings):  # noqa: ANN001, ARG002
        event_ids = input_pack.selected_event_ids[:1]
        source_ids = [source.source_id for source in external_evidence.sources]
        return OpportunityMemoStructuredArtifact.model_validate(
            {
                "title": "Natural Gas Supply Disruption Setup",
                "thesis": "Natural gas supply disruption is sustaining a repricing window in gas-linked markets.",
                "opportunity_target": "Short-horizon gas-linked spread and volatility positioning.",
                "background": "Clustered natural gas event evidence points to persistent supply-side stress.",
                "primary_driver": "Natural gas supply disruption remains dominant with repeated corroborating events.",
                "supporting_developments": [
                    "Operational natural gas curtailment signals and export frictions aligned in the same window."
                ],
                "why_now": "Natural gas temporal density and recency support immediate thesis relevance.",
                "action_path": "Allocate via liquid gas-linked instruments, stage entries around event confirmation cadence, and rebalance exposure when watchpoints weaken.",
                "risks": [
                    "Rapid restart progress could compress the pricing premium.",
                ],
                "watchpoints": [
                    "Official outage-restart timelines and shipping flow normalization signals.",
                ],
                "conclusion": "The setup is actionable with disciplined invalidation handling.",
                "traceability": {
                    "paragraph_sources": [
                        {"paragraph_key": "thesis", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
                        {"paragraph_key": "background", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
                        {"paragraph_key": "primary_driver", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
                        {"paragraph_key": "supporting_developments[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
                        {"paragraph_key": "why_now", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
                        {"paragraph_key": "action_path", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
                        {"paragraph_key": "risks[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
                        {"paragraph_key": "watchpoints[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
                        {"paragraph_key": "conclusion", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
                    ]
                },
            }
        )


def _settings() -> Settings:
    return Settings(
        opportunity_memo_topic_score_threshold=0.58,
        opportunity_memo_min_supporting_events=3,
        opportunity_memo_min_external_sources=3,
        opportunity_memo_openai_timeout_seconds=1.0,
        opportunity_memo_openai_max_retries=0,
        openai_api_key="test-key",
        openai_model="gpt-test",
    )


def test_workflow_persists_artifact_and_records_successful_delivery(monkeypatch):
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            _seed_natural_gas_events(db, now=now)
            db.commit()

        monkeypatch.setattr(opportunity_memo_pipeline, "send_telegram_text", lambda payload, settings=None: "msg-123")
        with SessionLocal() as db:
            result = run_opportunity_memo(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                settings=_settings(),
                research_provider=_FakeResearchProvider(),
                memo_writer=_FakeWriter(),
            )
            db.commit()

            assert result.status == "completed"
            assert result.artifact_id is not None
            assert db.query(OpportunityMemoRun).count() == 1
            assert db.query(OpportunityMemoArtifact).count() == 1
            assert db.query(OpportunityMemoInputEvent).count() >= 3
            assert db.query(OpportunityMemoExternalSource).count() == 3
            delivery = db.query(OpportunityMemoDelivery).one()
            assert delivery.status == "published"
            assert delivery.external_ref == "msg-123"
            first_artifact = db.query(OpportunityMemoArtifact).one()
            first_input_hash = first_artifact.input_hash
            first_canonical_hash = first_artifact.canonical_hash

            second = run_opportunity_memo(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                settings=_settings(),
                research_provider=_FakeResearchProvider(),
                memo_writer=_FakeWriter(),
            )
            db.commit()
            assert second.status == "completed"
            artifacts = db.query(OpportunityMemoArtifact).order_by(OpportunityMemoArtifact.id.asc()).all()
            assert len(artifacts) == 2
            assert artifacts[1].input_hash == first_input_hash
            assert artifacts[1].canonical_hash == first_canonical_hash
    finally:
        engine.dispose()


def test_workflow_records_delivery_failure_without_losing_artifact(monkeypatch):
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            _seed_natural_gas_events(db, now=now)
            db.commit()

        def _raise_delivery(payload, settings=None):  # noqa: ANN001, ARG001
            raise RuntimeError("telegram down")

        monkeypatch.setattr(opportunity_memo_pipeline, "send_telegram_text", _raise_delivery)
        with SessionLocal() as db:
            result = run_opportunity_memo(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                settings=_settings(),
                research_provider=_FakeResearchProvider(),
                memo_writer=_FakeWriter(),
            )
            db.commit()

            assert result.status == "delivery_failed"
            assert result.artifact_id is not None
            assert db.query(OpportunityMemoArtifact).count() == 1
            delivery = db.query(OpportunityMemoDelivery).one()
            assert delivery.status == "failed"
            assert "telegram down" in (delivery.last_error or "")
    finally:
        engine.dispose()


def test_workflow_auto_path_and_no_topic_found_path(monkeypatch):
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        monkeypatch.setattr(opportunity_memo_pipeline, "send_telegram_text", lambda payload, settings=None: "ok")

        with SessionLocal() as db:
            _seed_natural_gas_events(db, now=now)
            db.commit()

            auto_result = run_opportunity_memo(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic=None,
                settings=_settings(),
                research_provider=_FakeResearchProvider(),
                memo_writer=_FakeWriter(),
            )
            db.commit()
            assert auto_result.status == "completed"
            assert auto_result.selected_topic == "natural_gas"

        with SessionLocal() as db:
            empty_result = run_opportunity_memo(
                db,
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=2),
                topic=None,
                settings=_settings(),
                research_provider=_FakeResearchProvider(),
                memo_writer=_FakeWriter(),
            )
            db.commit()
            assert empty_result.status == "no_topic_found"
            assert empty_result.artifact_id is None
    finally:
        engine.dispose()

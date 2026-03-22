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
            "entities": {"countries": ["Qatar"], "orgs": ["Terminal Operator"], "people": [], "tickers": ["TTF"]},
            "market_stats": [{"label": "spread_move", "value": 1.8, "unit": "%", "context": "up"}],
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
                    summary="Storage fell 3.4% week-over-week.",
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
                    summary="Outage affected 6.2 mtpa equivalent capacity.",
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
                    summary="Regional spread widened 14% in the window.",
                    claim_support_tags=["risk"],
                    url="https://example.com/3",
                ),
            ],
            retrieval_diagnostics={"fake": True},
        )


def _traceability_rows(event_ids: list[int], source_ids: list[str]) -> list[dict]:
    return [
        {"paragraph_key": "core_thesis_one_liner", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "market_setup", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "background", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "primary_driver", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "supporting_developments[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "supporting_developments[1]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "why_now", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "why_this_is_an_opportunity", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "trade_expression", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "quantified_evidence_points[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "quantified_evidence_points[1]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "risks[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "risks[1]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "invalidation_triggers[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "invalidation_triggers[1]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "watchpoints[0]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
        {"paragraph_key": "watchpoints[1]", "internal_event_ids": event_ids, "external_source_ids": source_ids[:2]},
        {"paragraph_key": "conclusion", "internal_event_ids": event_ids, "external_source_ids": source_ids[:1]},
    ]


class _SharpWriter:
    name = "sharp_writer"

    def write(self, *, input_pack, external_evidence, settings):  # noqa: ANN001, ARG002
        event_ids = input_pack.selected_event_ids[:2]
        source_ids = [source.source_id for source in external_evidence.sources]
        return OpportunityMemoStructuredArtifact.model_validate(
            {
                "title": "Northwest Europe Gas Tightening Repricing",
                "core_thesis_one_liner": "Northwest Europe gas spread upside is actionable because clustered supply disruption and storage draw signals accelerated in the window.",
                "opportunity_target": "TTF front-month vs deferred spread and gas-sensitive utility hedge books.",
                "market_setup": "Supply curtailment events and flow frictions aligned with storage draw pressure, reinforcing prompt spread repricing.",
                "background": "Windowed event evidence captured repeated high-impact disruptions in LNG-linked gas flows.",
                "primary_driver": "supply_disruption dominates event support and timing concentration.",
                "supporting_developments": [
                    "Terminal curtailment updates persisted across two sessions.",
                    "Prompt-deferred curve steepening aligned with freight pressure.",
                ],
                "why_now": "Recent event density rose within the current window while numeric storage and spread datapoints confirmed immediate timing risk.",
                "why_this_is_an_opportunity": "Transmission into spread repricing appears underappreciated relative to consensus hedge posture, leaving risk premium expansion potential.",
                "trade_expression": "Express through liquid gas spread futures and optionality overlays tied to TTF curve steepening and explicit invalidation levels.",
                "quantified_evidence_points": [
                    "Storage fell 3.4% week-over-week during the memo window.",
                    "Outage impact reached 6.2 mtpa while regional spread widened 14%.",
                ],
                "risks": [
                    "Faster-than-expected restart can compress spreads.",
                    "Policy intervention can dampen pass-through mechanics.",
                ],
                "invalidation_triggers": [
                    "Verified restart of constrained nodes ahead of guidance.",
                    "Two-session spread compression with normalized flow data.",
                ],
                "watchpoints": [
                    "Terminal restart bulletins and vessel loading cadence.",
                    "Storage trajectory and prompt/deferred spread behavior.",
                ],
                "confidence_level": "medium",
                "conclusion": "Setup remains actionable while disruption-linked repricing persists and invalidation conditions stay unmet.",
                "traceability": {"paragraph_sources": _traceability_rows(event_ids, source_ids)},
            }
        )


class _GenericWriter:
    name = "generic_writer"

    def write(self, *, input_pack, external_evidence, settings):  # noqa: ANN001, ARG002
        return OpportunityMemoStructuredArtifact.model_validate(
            {
                "title": "Energy Sector Update",
                "core_thesis_one_liner": "Energy markets could see movement.",
                "opportunity_target": "energy markets",
                "market_setup": "The sector is evolving.",
                "background": "There were several updates.",
                "primary_driver": "market uncertainty",
                "supporting_developments": ["Various factors are in play.", "Things are changing."],
                "why_now": "This continues to matter over time.",
                "why_this_is_an_opportunity": "This is important for investors.",
                "trade_expression": "Investors should monitor developments and diversify.",
                "quantified_evidence_points": ["This seems meaningful.", "It could matter."],
                "risks": ["Market uncertainty remains.", "Many outcomes are possible."],
                "invalidation_triggers": ["Sentiment changes.", "General developments."],
                "watchpoints": ["Monitor developments.", "Stay informed."],
                "confidence_level": "high",
                "conclusion": "Overall this is worth watching.",
                "traceability": {"paragraph_sources": []},
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


def test_workflow_persists_updated_artifact_and_records_successful_delivery(monkeypatch):
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
                memo_writer=_SharpWriter(),
            )
            db.commit()

            assert result.status == "completed"
            assert result.artifact_id is not None
            artifact = db.query(OpportunityMemoArtifact).one()
            assert artifact.memo_json["core_thesis_one_liner"]
            assert artifact.memo_json["trade_expression"]
            assert len(artifact.memo_json["quantified_evidence_points"]) >= 2
            first_input_hash = artifact.input_hash
            first_canonical_hash = artifact.canonical_hash
            assert first_input_hash
            assert first_canonical_hash
            assert db.query(OpportunityMemoRun).count() == 1
            assert db.query(OpportunityMemoInputEvent).count() >= 3
            assert db.query(OpportunityMemoExternalSource).count() == 3
            delivery = db.query(OpportunityMemoDelivery).one()
            assert delivery.status == "published"
            assert delivery.external_ref == "msg-123"

            second = run_opportunity_memo(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                settings=_settings(),
                research_provider=_FakeResearchProvider(),
                memo_writer=_SharpWriter(),
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
                memo_writer=_SharpWriter(),
            )
            db.commit()

            assert result.status == "delivery_failed"
            assert result.artifact_id is not None
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
                memo_writer=_SharpWriter(),
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
                memo_writer=_SharpWriter(),
            )
            db.commit()
            assert empty_result.status == "no_topic_found"
            assert empty_result.artifact_id is None
    finally:
        engine.dispose()


def test_workflow_fails_validation_for_generic_memo_output(monkeypatch):
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        monkeypatch.setattr(opportunity_memo_pipeline, "send_telegram_text", lambda payload, settings=None: "ok")

        with SessionLocal() as db:
            _seed_natural_gas_events(db, now=now)
            db.commit()
            result = run_opportunity_memo(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                settings=_settings(),
                research_provider=_FakeResearchProvider(),
                memo_writer=_GenericWriter(),
            )
            db.commit()
            assert result.status == "validation_failed"
            assert result.artifact_id is None
            run = db.query(OpportunityMemoRun).order_by(OpportunityMemoRun.id.desc()).first()
            assert run is not None
            assert isinstance(run.validation_errors_json, list)
            assert any(row.get("code") in {"generic_opportunity_target", "insufficient_quantified_evidence"} for row in run.validation_errors_json)
    finally:
        engine.dispose()

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.schemas import ExtractionEntities, ExtractionJson
from app.contexts.enrichment.enrichment_selection import select_and_store_enrichment_candidate
from app.contexts.triage.impact_scoring import ImpactCalibrationResult


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def _extraction(*, fingerprint: str, summary: str) -> ExtractionJson:
    return ExtractionJson(
        topic="macro_econ",
        entities=ExtractionEntities(
            countries=["United States"],
            orgs=["Federal Reserve"],
            people=[],
            tickers=["DXY"],
        ),
        affected_countries_first_order=["United States"],
        market_stats=[],
        sentiment="neutral",
        confidence=0.85,
        impact_score=85.0,
        is_breaking=True,
        breaking_window="15m",
        event_time=datetime.utcnow(),
        source_claimed="Reuters",
        summary_1_sentence=summary,
        keywords=["cpi", "yield", "usd"],
        event_core=None,
        event_fingerprint=fingerprint,
    )


def _calibration(score: float = 86.0, *, route: str | None = None) -> ImpactCalibrationResult:
    resolved_route = route or ("deep_enrich" if score >= 80.0 else ("index_only" if score >= 45.0 else "store_only"))
    return ImpactCalibrationResult(
        raw_llm_score=65.0,
        calibrated_score=score,
        score_band="top" if score >= 80 else "high",
        enrichment_route=resolved_route,
        shock_flags=["major_macroeconomic_surprise"] if score >= 80 else [],
        rules_fired=["impact:shock_transmission_confirmed_boost"],
        score_breakdown={
            "components": {
                "severity": 20,
                "economic_relevance": 18,
                "propagation_potential": 17,
                "specificity": 10,
                "novelty_signal": 7,
                "strategic_relevance": 5,
            },
            "dimensions": {
                "market_relevance": 28,
                "economic_magnitude": 20,
                "transmission_clarity": 22,
                "urgency": 10,
            },
            "enrichment_route": resolved_route,
            "transmission_criteria_met": True,
            "score_band_computed_after_rules": True,
            "final_score": score,
        },
    )


def test_enrichment_selection_is_novel_and_high_impact():
    SessionLocal, engine = _session_factory()

    from app.models import Event

    try:
        with SessionLocal() as db:
            event = Event(
                event_fingerprint="f1",
                topic="macro_econ",
                summary_1_sentence="US CPI surprise hits rates.",
                impact_score=80.0,
                is_breaking=True,
                breaking_window="15m",
                event_time=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            db.add(event)
            db.flush()

            row = select_and_store_enrichment_candidate(
                db,
                event_id=event.id,
                extraction=_extraction(fingerprint="f1", summary="US CPI surprise significantly above expectations."),
                calibration=_calibration(86.0),
                triage_action="promote",
                triage_rules=["triage:new_event_promote"],
                existing_event_id=None,
            )
            db.commit()

            assert row.selected is True
            assert row.novelty_state == "novel"
            assert "enrichment:selected" in row.reason_codes
    finally:
        engine.dispose()


def test_enrichment_selection_blocks_existing_event_lineage():
    SessionLocal, engine = _session_factory()

    from app.models import Event

    try:
        with SessionLocal() as db:
            event = Event(
                event_fingerprint="f2",
                topic="macro_econ",
                summary_1_sentence="Existing event summary.",
                impact_score=82.0,
                is_breaking=True,
                breaking_window="15m",
                event_time=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            db.add(event)
            db.flush()

            row = select_and_store_enrichment_candidate(
                db,
                event_id=event.id,
                extraction=_extraction(fingerprint="f2", summary="Follow-on update for same event."),
                calibration=_calibration(88.0),
                triage_action="update",
                triage_rules=["triage:related_material_update"],
                existing_event_id=event.id,
            )
            db.commit()

            assert row.selected is False
            assert row.novelty_state == "blocked_event_lineage"
            assert "enrichment:novelty_block_event_lineage" in row.reason_codes
    finally:
        engine.dispose()


def test_enrichment_selection_blocks_duplicate_cluster_and_triage_markers():
    SessionLocal, engine = _session_factory()

    from app.models import EnrichmentCandidate, Event

    try:
        with SessionLocal() as db:
            first_event = Event(
                event_fingerprint="dup-fp",
                topic="macro_econ",
                summary_1_sentence="Initial shock event.",
                impact_score=84.0,
                is_breaking=True,
                breaking_window="15m",
                event_time=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            second_event = Event(
                event_fingerprint="dup-fp-2",
                topic="macro_econ",
                summary_1_sentence="Near duplicate shock event.",
                impact_score=84.0,
                is_breaking=True,
                breaking_window="15m",
                event_time=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            db.add(first_event)
            db.add(second_event)
            db.flush()

            prior = EnrichmentCandidate(
                event_id=first_event.id,
                selected=True,
                triage_action="promote",
                reason_codes=["enrichment:selected"],
                novelty_state="novel",
                novelty_cluster_key="dup-fp",
                calibrated_score=85.0,
                raw_llm_score=70.0,
                score_band="top",
                shock_flags=["major_macroeconomic_surprise"],
                score_breakdown={"transmission_criteria_met": True},
                scored_at=datetime.utcnow(),
            )
            db.add(prior)
            db.flush()

            row = select_and_store_enrichment_candidate(
                db,
                event_id=second_event.id,
                extraction=_extraction(fingerprint="dup-fp", summary="Near duplicate development."),
                calibration=_calibration(85.0),
                triage_action="promote",
                triage_rules=["triage:burst_cap_monitor"],
                existing_event_id=None,
            )
            db.commit()

            assert row.selected is False
            assert row.novelty_state in {"blocked_duplicate_marker", "blocked_cluster_repeat"}
            assert any(code.startswith("enrichment:novelty_block") for code in row.reason_codes)
    finally:
        engine.dispose()


def test_enrichment_selection_skips_non_deep_route():
    SessionLocal, engine = _session_factory()

    from app.models import Event

    try:
        with SessionLocal() as db:
            event = Event(
                event_fingerprint="route-fp",
                topic="macro_econ",
                summary_1_sentence="Moderate update.",
                impact_score=52.0,
                is_breaking=False,
                breaking_window="none",
                event_time=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            db.add(event)
            db.flush()

            row = select_and_store_enrichment_candidate(
                db,
                event_id=event.id,
                extraction=_extraction(fingerprint="route-fp", summary="Moderate update."),
                calibration=_calibration(52.0, route="index_only"),
                triage_action="monitor",
                triage_rules=["triage:score_band:medium"],
                existing_event_id=None,
            )
            db.commit()

            assert row.selected is False
            assert row.enrichment_route == "index_only"
            assert "enrichment:not_eligible_route" in row.reason_codes
    finally:
        engine.dispose()


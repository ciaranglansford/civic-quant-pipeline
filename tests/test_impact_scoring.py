from __future__ import annotations

from datetime import datetime

from app.schemas import ExtractionEntities, ExtractionJson, MarketStat
from app.contexts.triage.impact_scoring import calibrate_impact, distribution_metrics


def _extraction(
    *,
    topic: str,
    summary: str,
    impact: float,
    breaking_window: str = "none",
    is_breaking: bool = False,
    keywords: list[str] | None = None,
    tickers: list[str] | None = None,
    market_stats: list[MarketStat] | None = None,
    tags: list[dict[str, object]] | None = None,
    impact_inputs: dict[str, list[str]] | None = None,
) -> ExtractionJson:
    return ExtractionJson(
        topic=topic,  # type: ignore[arg-type]
        entities=ExtractionEntities(
            countries=["United States"],
            orgs=["Federal Reserve"],
            people=[],
            tickers=tickers or [],
        ),
        affected_countries_first_order=["United States"],
        market_stats=market_stats or [],
        sentiment="neutral",
        confidence=0.85,
        impact_score=impact,
        is_breaking=is_breaking,
        breaking_window=breaking_window,  # type: ignore[arg-type]
        event_time=datetime.utcnow(),
        source_claimed="Reuters",
        summary_1_sentence=summary,
        keywords=keywords or [],
        event_core=None,
        event_fingerprint="f",
        tags=tags or [],
        impact_inputs=impact_inputs or {},
    )


def test_no_shock_blocks_top_band_even_with_high_raw_score():
    extraction = _extraction(
        topic="macro_econ",
        summary="Officials discuss inflation outlook and policy framework.",
        impact=98.0,
        keywords=["inflation", "policy"],
        tickers=["DXY"],
    )

    out = calibrate_impact(extraction)
    assert out.raw_llm_score == 98.0
    assert out.calibrated_score < 80.0
    assert out.enrichment_route in {"store_only", "index_only"}
    assert "impact:no_shock_top_band_block" in out.rules_fired
    assert out.score_breakdown["score_band_computed_after_rules"] is True
    components = out.score_breakdown["components"]
    assert set(components.keys()) == {
        "severity",
        "economic_relevance",
        "propagation_potential",
        "specificity",
        "novelty_signal",
        "strategic_relevance",
    }


def test_local_incident_cap_applies_regardless_of_raw_score():
    extraction = _extraction(
        topic="war_security",
        summary="Police report multiple people injured in Austin, TX incident.",
        impact=95.0,
        breaking_window="15m",
        is_breaking=True,
        keywords=["police", "incident", "injured"],
    )

    out = calibrate_impact(extraction)
    assert out.raw_llm_score == 95.0
    assert out.calibrated_score <= 40.0
    assert out.enrichment_route == "store_only"
    assert "impact:local_incident_cap_40" in out.rules_fired


def test_top_band_requires_shock_and_transmission():
    extraction = _extraction(
        topic="macro_econ",
        summary="US CPI surprise significantly above expectations; Treasury yields jump 35 bps and USD surges.",
        impact=42.0,
        breaking_window="15m",
        is_breaking=True,
        keywords=["cpi surprise", "yields", "usd"],
        tickers=["DXY"],
        market_stats=[MarketStat(label="US10Y", value=35.0, unit="bps", context="move")],
    )

    out = calibrate_impact(extraction)
    assert out.calibrated_score >= 80.0
    assert out.score_band == "top"
    assert out.enrichment_route == "deep_enrich"
    assert "major_macroeconomic_surprise" in out.shock_flags
    assert out.score_breakdown["transmission_criteria_met"] is True


def test_route_assignment_is_deterministic_across_repeated_runs():
    extraction = _extraction(
        topic="commodities",
        summary="Export restriction disrupts logistics for oil shipments.",
        impact=71.0,
        breaking_window="1h",
        is_breaking=True,
        keywords=["export restriction", "oil", "logistics"],
        market_stats=[MarketStat(label="Brent", value=2.2, unit="%", context="move")],
        tags=[
            {"tag_type": "strategic", "tag_value": "supply_risk", "tag_source": "observed", "confidence": 0.8}
        ],
        impact_inputs={
            "severity_cues": ["restriction"],
            "economic_relevance_cues": ["oil"],
            "propagation_potential_cues": ["logistics"],
            "specificity_cues": ["shipment"],
            "novelty_cues": ["new restriction"],
            "strategic_tag_hits": ["supply_risk"],
        }
    )
    first = calibrate_impact(extraction)
    second = calibrate_impact(extraction)
    assert first.calibrated_score == second.calibrated_score
    assert first.enrichment_route == second.enrichment_route
    assert first.score_breakdown["components"] == second.score_breakdown["components"]


def test_distribution_metrics_include_percentiles_and_thresholds():
    metrics = distribution_metrics([10.0, 40.0, 61.0, 79.0, 80.0, 92.0])
    assert metrics["count"] == 6.0
    assert metrics["p95"] >= 80.0
    assert metrics["p99"] >= metrics["p95"]
    assert metrics["pct_gt_40"] > 0
    assert metrics["pct_gt_60"] > 0
    assert metrics["pct_gte_80"] > 0


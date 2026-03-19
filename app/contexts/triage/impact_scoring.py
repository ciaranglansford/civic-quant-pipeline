from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ...schemas import ExtractionJson
from .triage_engine import is_local_domestic_incident


@dataclass(frozen=True)
class ImpactCalibrationResult:
    raw_llm_score: float
    calibrated_score: float
    score_band: str
    enrichment_route: str
    shock_flags: list[str]
    rules_fired: list[str]
    score_breakdown: dict[str, object]


_TOPIC_RELEVANCE_SCORE = {
    "central_banks": 30,
    "macro_econ": 28,
    "rates": 24,
    "credit": 24,
    "fx": 22,
    "commodities": 22,
    "war_security": 20,
    "geopolitics": 18,
    "equities": 18,
    "crypto": 16,
    "company_specific": 14,
    "other": 8,
}

_URGENCY_SCORE = {
    "15m": 10,
    "1h": 7,
    "4h": 4,
    "none": 1,
}

_TRANSMISSION_MARKERS = (
    "yield",
    "yields",
    "spread",
    "spreads",
    "rate",
    "rates",
    "funding",
    "liquidity",
    "inflation",
    "growth",
    "recession",
    "credit",
    "oil",
    "gas",
    "brent",
    "wti",
    "currency",
    "fx",
    "usd",
    "eur",
    "jpy",
    "equity",
    "stocks",
    "bond",
    "bonds",
    "commodity",
    "commodities",
    "exports",
    "imports",
    "sanction",
    "capital control",
)

_SHOCK_TAXONOMY = {
    "central_bank_rate_change": (
        "rate hike",
        "rate cut",
        "hike rates",
        "cut rates",
        "policy rate",
        "fomc",
        "ecb",
        "boj",
        "boe",
    ),
    "sovereign_default": (
        "sovereign default",
        "government default",
        "debt default",
        "missed coupon",
    ),
    "major_bank_failure": (
        "bank failure",
        "bank collapse",
        "insolvency",
        "bank run",
    ),
    "war_outbreak": (
        "war outbreak",
        "invaded",
        "invasion",
        "major offensive",
        "missile barrage",
        "airstrike",
    ),
    "large_scale_sanctions": (
        "sweeping sanctions",
        "broad sanctions",
        "large-scale sanctions",
        "export controls",
    ),
    "major_commodity_disruption": (
        "supply disruption",
        "pipeline shutdown",
        "strait of hormuz",
        "production halt",
        "major opec cut",
    ),
    "systemic_financial_crisis": (
        "systemic crisis",
        "financial crisis",
        "credit crunch",
        "liquidity crisis",
    ),
    "major_macroeconomic_surprise": (
        "major surprise",
        "significantly above expectations",
        "significantly below expectations",
        "cpi surprise",
        "jobs surprise",
        "gdp surprise",
    ),
}

_WS_RE = re.compile(r"\s+")
_PERCENT_BPS_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(%|bp|bps)\b", re.IGNORECASE)


def _normalize_text(*parts: str | None) -> str:
    joined = " ".join(p or "" for p in parts)
    return _WS_RE.sub(" ", joined.strip()).lower()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def _score_band(score: float) -> str:
    if score >= 80.0:
        return "top"
    if score >= 60.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _max_band_for_score(max_score: float) -> str:
    return _score_band(max_score)


def _market_relevance_score(extraction: ExtractionJson, *, local_incident: bool) -> int:
    if local_incident:
        return 5
    return _TOPIC_RELEVANCE_SCORE.get(extraction.topic, 8)


def _economic_magnitude_score(extraction: ExtractionJson, text: str) -> int:
    score = 0
    market_stats_count = len(extraction.market_stats)
    score += min(12, market_stats_count * 4)
    if _PERCENT_BPS_RE.search(text):
        score += 6
    if _contains_any(
        text,
        (
            "default",
            "collapse",
            "failure",
            "emergency",
            "surprise",
            "recession",
            "sanctions",
            "halt",
            "cut production",
            "hike",
            "cut",
        ),
    ):
        score += 8
    countries = len(extraction.affected_countries_first_order or extraction.entities.countries)
    if countries >= 2:
        score += 4
    return min(30, score)


def _transmission_clarity_score(extraction: ExtractionJson, text: str) -> int:
    score = 0
    if _contains_any(text, _TRANSMISSION_MARKERS):
        score += 10
    if extraction.market_stats:
        score += 8
    if extraction.entities.tickers:
        score += 4
    if extraction.topic in {"central_banks", "macro_econ", "rates", "credit", "fx", "commodities"}:
        score += 5
    return min(25, score)


def _urgency_score(extraction: ExtractionJson) -> int:
    score = _URGENCY_SCORE.get(extraction.breaking_window, 1)
    if extraction.is_breaking and extraction.breaking_window == "none":
        score = min(10, score + 2)
    return score


def _shock_flags(extraction: ExtractionJson, text: str) -> list[str]:
    found: list[str] = []

    for flag, markers in _SHOCK_TAXONOMY.items():
        if _contains_any(text, markers):
            found.append(flag)

    # Topic-aware deterministic guards for ambiguous text.
    if extraction.topic == "central_banks" and _contains_any(text, _SHOCK_TAXONOMY["central_bank_rate_change"]):
        if "central_bank_rate_change" not in found:
            found.append("central_bank_rate_change")
    if extraction.topic == "macro_econ" and "major_macroeconomic_surprise" in found:
        pass
    if extraction.topic == "commodities" and _contains_any(text, _SHOCK_TAXONOMY["major_commodity_disruption"]):
        if "major_commodity_disruption" not in found:
            found.append("major_commodity_disruption")
    if extraction.topic == "war_security" and _contains_any(text, _SHOCK_TAXONOMY["war_outbreak"]):
        if "war_outbreak" not in found:
            found.append("war_outbreak")

    return sorted(set(found))


def _cue_bonus(cues: list[str], *, step: int, max_bonus: int) -> int:
    if not cues:
        return 0
    return min(max_bonus, len(cues) * step)


def _specificity_component(extraction: ExtractionJson, text: str) -> int:
    score = 0
    if extraction.market_stats:
        score += min(6, len(extraction.market_stats) * 2)
    if extraction.entities.tickers:
        score += min(3, len(extraction.entities.tickers))
    if len(extraction.keywords) >= 3:
        score += 3
    if extraction.event_time is not None:
        score += 2
    if _PERCENT_BPS_RE.search(text):
        score += 2
    score += _cue_bonus(extraction.impact_inputs.specificity_cues, step=2, max_bonus=4)
    return min(15, score)


def _novelty_component(extraction: ExtractionJson, *, shock_flags: list[str]) -> int:
    score = 0
    if extraction.is_breaking:
        score += 4
    if extraction.breaking_window in {"15m", "1h"}:
        score += 2
    if extraction.event_time is not None:
        score += 1
    if shock_flags:
        score += 2
    score += _cue_bonus(extraction.impact_inputs.novelty_cues, step=2, max_bonus=4)
    return min(10, score)


def _strategic_component(extraction: ExtractionJson) -> tuple[int, list[str]]:
    strategic_hits = sorted(
        {
            (tag.tag_value or "").strip().lower()
            for tag in extraction.tags
            if tag.tag_type == "strategic" and tag.tag_value
        }
        | {(value or "").strip().lower() for value in extraction.impact_inputs.strategic_tag_hits if value}
    )
    score = 0
    if strategic_hits:
        score += min(8, len(strategic_hits) * 3)
    if extraction.topic in {"war_security", "geopolitics", "commodities"}:
        score += 2
    return min(10, score), strategic_hits


def _route_for_score(
    *,
    calibrated_score: float,
    strategic_relevance: int,
    strategic_hits: list[str],
    local_incident: bool,
) -> str:
    if local_incident:
        return "store_only"
    if calibrated_score >= 80.0 or strategic_relevance >= 8 or len(strategic_hits) >= 2:
        return "deep_enrich"
    if calibrated_score >= 45.0:
        return "index_only"
    return "store_only"


def calibrate_impact(extraction: ExtractionJson) -> ImpactCalibrationResult:
    raw_llm_score = float(extraction.impact_score)
    text = _normalize_text(
        extraction.summary_1_sentence,
        extraction.source_claimed,
        " ".join(extraction.keywords),
    )

    local_incident = is_local_domestic_incident(extraction)
    market_relevance = _market_relevance_score(extraction, local_incident=local_incident)
    magnitude = _economic_magnitude_score(extraction, text)
    transmission = _transmission_clarity_score(extraction, text)
    urgency = _urgency_score(extraction)
    shock_flags = _shock_flags(extraction, text)
    has_market_link = bool(extraction.market_stats or extraction.entities.tickers or _contains_any(text, _TRANSMISSION_MARKERS))
    transmission_criteria_met = transmission >= 15 and has_market_link

    severity = min(
        25,
        magnitude
        + (6 if shock_flags else 0)
        + _cue_bonus(extraction.impact_inputs.severity_cues, step=2, max_bonus=6),
    )
    economic_relevance = min(
        20,
        int(round(market_relevance * 0.6))
        + _cue_bonus(extraction.impact_inputs.economic_relevance_cues, step=2, max_bonus=6),
    )
    propagation_potential = min(
        20,
        int(round(transmission * 0.6))
        + _cue_bonus(extraction.impact_inputs.propagation_potential_cues, step=2, max_bonus=6),
    )
    specificity = _specificity_component(extraction, text)
    novelty_signal = _novelty_component(extraction, shock_flags=shock_flags)
    strategic_relevance, strategic_hits = _strategic_component(extraction)

    component_score = float(
        severity
        + economic_relevance
        + propagation_potential
        + specificity
        + novelty_signal
        + strategic_relevance
    )
    base_rule_score = component_score + (urgency * 0.4)
    score = base_rule_score

    rules_fired: list[str] = []
    boosts: list[dict[str, object]] = []
    caps: list[dict[str, object]] = []
    max_allowed_score = 100.0

    if shock_flags and transmission_criteria_met and magnitude >= 12:
        score += 8.0
        rules_fired.append("impact:shock_transmission_confirmed_boost")
        boosts.append({"rule": "shock_transmission_confirmed_boost", "delta": 8.0})
    if len(shock_flags) >= 2:
        score += 4.0
        rules_fired.append("impact:multi_shock_boost")
        boosts.append({"rule": "multi_shock_boost", "delta": 4.0})
    if extraction.breaking_window in {"15m", "1h"} and shock_flags:
        score += 3.0
        rules_fired.append("impact:breaking_shock_boost")
        boosts.append({"rule": "breaking_shock_boost", "delta": 3.0})

    if local_incident:
        max_allowed_score = min(max_allowed_score, 40.0)
        rules_fired.append("impact:local_incident_cap_40")
        caps.append({"rule": "local_incident_cap_40", "max_score": 40.0})

    if market_relevance < 12 and not extraction.market_stats and not extraction.entities.tickers:
        max_allowed_score = min(max_allowed_score, 45.0)
        rules_fired.append("impact:non_market_cap_45")
        caps.append({"rule": "non_market_cap_45", "max_score": 45.0})

    if transmission < 10:
        max_allowed_score = min(max_allowed_score, 60.0)
        rules_fired.append("impact:low_transmission_cap_60")
        caps.append({"rule": "low_transmission_cap_60", "max_score": 60.0})

    if not shock_flags:
        max_allowed_score = min(max_allowed_score, 79.0)
        rules_fired.append("impact:no_shock_top_band_block")
        caps.append({"rule": "no_shock_top_band_block", "max_score": 79.0})

    if not transmission_criteria_met:
        max_allowed_score = min(max_allowed_score, 79.0)
        rules_fired.append("impact:transmission_top_band_block")
        caps.append({"rule": "transmission_top_band_block", "max_score": 79.0})

    if strategic_hits:
        rules_fired.append("impact:strategic_relevance_signal")

    pre_cap_score = score
    final_score = float(max(0.0, min(100.0, min(score, max_allowed_score))))
    calibrated_score = int(round(final_score))
    score_band = _score_band(float(calibrated_score))
    enrichment_route = _route_for_score(
        calibrated_score=float(calibrated_score),
        strategic_relevance=strategic_relevance,
        strategic_hits=strategic_hits,
        local_incident=local_incident,
    )
    rules_fired.append(f"impact:route:{enrichment_route}")

    score_breakdown: dict[str, object] = {
        "components": {
            "severity": severity,
            "economic_relevance": economic_relevance,
            "propagation_potential": propagation_potential,
            "specificity": specificity,
            "novelty_signal": novelty_signal,
            "strategic_relevance": strategic_relevance,
        },
        "dimensions": {
            "market_relevance": market_relevance,
            "economic_magnitude": magnitude,
            "transmission_clarity": transmission,
            "urgency": urgency,
        },
        "strategic_hits": strategic_hits,
        "base_rule_score": base_rule_score,
        "pre_cap_score": pre_cap_score,
        "max_allowed_score": max_allowed_score,
        "max_allowed_band": _max_band_for_score(max_allowed_score),
        "transmission_criteria_met": transmission_criteria_met,
        "local_incident": local_incident,
        "enrichment_route": enrichment_route,
        "raw_score_used_as_authoritative": False,
        "caps_applied": caps,
        "boosts_applied": boosts,
        "score_band_computed_after_rules": True,
        "final_score": float(calibrated_score),
    }

    return ImpactCalibrationResult(
        raw_llm_score=raw_llm_score,
        calibrated_score=float(calibrated_score),
        score_band=score_band,
        enrichment_route=enrichment_route,
        shock_flags=shock_flags,
        rules_fired=rules_fired,
        score_breakdown=score_breakdown,
    )


def _percentile_nearest_rank(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    rank = max(1, math.ceil((p / 100.0) * len(sorted_vals)))
    return float(sorted_vals[rank - 1])


def distribution_metrics(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "pct_gt_40": 0.0,
            "pct_gt_60": 0.0,
            "pct_gte_80": 0.0,
        }

    total = float(len(values))
    pct_gt_40 = 100.0 * sum(1 for v in values if v > 40.0) / total
    pct_gt_60 = 100.0 * sum(1 for v in values if v > 60.0) / total
    pct_gte_80 = 100.0 * sum(1 for v in values if v >= 80.0) / total

    return {
        "count": total,
        "p95": round(_percentile_nearest_rank(values, 95.0), 2),
        "p99": round(_percentile_nearest_rank(values, 99.0), 2),
        "pct_gt_40": round(pct_gt_40, 2),
        "pct_gt_60": round(pct_gt_60, 2),
        "pct_gte_80": round(pct_gte_80, 2),
    }


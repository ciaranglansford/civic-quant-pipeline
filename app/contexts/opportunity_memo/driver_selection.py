from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from .constants import DRIVER_KEYS, DRIVER_SCORE_WEIGHTS
from .contracts import DriverCandidate, DriverScoreComponents


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _impact(event: dict[str, Any]) -> float:
    raw = event.get("impact_score")
    if isinstance(raw, (int, float)):
        return _clamp01(float(raw) / 100.0)
    return 0.0


def _event_time(event: dict[str, Any]) -> datetime | None:
    raw = event.get("event_time") or event.get("last_updated_at")
    return raw if isinstance(raw, datetime) else None


def _event_text(event: dict[str, Any]) -> str:
    parts: list[str] = []
    summary = event.get("summary_1_sentence")
    if isinstance(summary, str):
        parts.append(summary.lower())

    payload = event.get("latest_extraction_payload")
    if isinstance(payload, dict):
        keywords = payload.get("keywords")
        if isinstance(keywords, list):
            for keyword in keywords:
                if isinstance(keyword, str):
                    parts.append(keyword.lower())

    for relation in event.get("relations") or []:
        if not isinstance(relation, dict):
            continue
        for key in ("relation_type", "subject_value", "object_value"):
            value = relation.get(key)
            if isinstance(value, str):
                parts.append(value.lower())

    return " ".join(parts)


def _driver_hits(event: dict[str, Any]) -> set[str]:
    text = _event_text(event)
    hits: set[str] = set()

    if any(token in text for token in ("disruption", "outage", "shutdown", "restriction", "curtail")):
        hits.add("supply_disruption")
    if any(token in text for token in ("demand", "consumption", "import growth", "demand surge")):
        hits.add("demand_acceleration")
    if any(token in text for token in ("inventory", "stockpile", "storage", "draw", "build")):
        hits.add("inventory_shift")
    if any(token in text for token in ("policy", "regulation", "sanction", "tariff", "quota", "mandate")):
        hits.add("policy_change")
    if any(token in text for token in ("shipping", "freight", "route", "spread", "repricing", "arbitrage")):
        hits.add("trade_flow_repricing")
    if any(token in text for token in ("weather", "storm", "freeze", "drought", "heatwave")):
        hits.add("weather_shock")
    if any(token in text for token in ("price", "cost", "feedstock", "margin", "input cost")):
        hits.add("input_cost_pressure")

    if not hits:
        hits.add("input_cost_pressure")
    return hits


def _entity_tokens(event: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    payload = event.get("latest_extraction_payload")
    if isinstance(payload, dict):
        entities = payload.get("entities")
        if isinstance(entities, dict):
            for key in ("countries", "orgs", "people", "tickers"):
                values = entities.get(key)
                if not isinstance(values, list):
                    continue
                for value in values:
                    if isinstance(value, str) and value.strip():
                        tokens.append(f"{key}:{value.strip().lower()}")
    return tokens


def _driver_component_supporting_event_weight(
    events: list[dict[str, Any]],
    supporting_event_ids: list[int],
) -> float:
    if not events or not supporting_event_ids:
        return 0.0

    total_impact = sum(_impact(event) for event in events)
    if total_impact <= 0.0:
        return 0.0

    supporting_ids = set(supporting_event_ids)
    supporting_impact = sum(_impact(event) for event in events if int(event.get("id") or 0) in supporting_ids)
    return _clamp01(supporting_impact / total_impact)


def _driver_component_temporal_density(
    supporting_events: list[dict[str, Any]],
    *,
    start_time: datetime,
    end_time: datetime,
) -> float:
    if not supporting_events:
        return 0.0

    timestamps = [ts for ts in (_event_time(event) for event in supporting_events) if ts is not None]
    if len(timestamps) <= 1:
        return 0.35

    span_hours = max(1.0, (max(timestamps) - min(timestamps)).total_seconds() / 3600.0)
    events_per_12h = len(timestamps) / max(1.0, span_hours / 12.0)
    window_hours = max(1.0, (end_time - start_time).total_seconds() / 3600.0)
    window_scale = min(1.0, 24.0 / window_hours)
    return _clamp01((events_per_12h / 2.5) * window_scale)


def _driver_component_entity_consistency(supporting_events: list[dict[str, Any]]) -> float:
    if not supporting_events:
        return 0.0

    entity_counts: Counter[str] = Counter()
    for event in supporting_events:
        entity_counts.update(_entity_tokens(event))

    if not entity_counts:
        return 0.30

    return _clamp01(max(entity_counts.values()) / float(sum(entity_counts.values())))


def _driver_component_external_confirmability_proxy(supporting_events: list[dict[str, Any]]) -> float:
    if not supporting_events:
        return 0.0

    score = 0.0
    if len(supporting_events) >= 2:
        score += 0.50
    elif len(supporting_events) == 1:
        score += 0.30

    relation_types = {
        str(relation.get("relation_type", "")).strip().lower()
        for event in supporting_events
        for relation in (event.get("relations") or [])
        if isinstance(relation, dict)
    }
    if relation_types & {
        "restricts_export_of",
        "curtails",
        "disrupts_logistics_of",
        "supports",
        "expands_production_of",
        "sanctions",
    }:
        score += 0.30

    avg_impact = sum(_impact(event) for event in supporting_events) / float(len(supporting_events))
    if avg_impact >= 0.60:
        score += 0.20

    return _clamp01(score)


def select_primary_driver(
    *,
    topic_events: list[dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
) -> tuple[list[DriverCandidate], DriverCandidate | None]:
    driver_to_event_ids: dict[str, set[int]] = defaultdict(set)

    for event in topic_events:
        event_id = int(event.get("id") or 0)
        if event_id <= 0:
            continue
        for driver_key in _driver_hits(event):
            driver_to_event_ids[driver_key].add(event_id)

    candidates: list[DriverCandidate] = []
    for driver_key in DRIVER_KEYS:
        supporting_event_ids = sorted(driver_to_event_ids.get(driver_key, set()))
        supporting_events = [
            event for event in topic_events if int(event.get("id") or 0) in set(supporting_event_ids)
        ]

        supporting_event_weight = _driver_component_supporting_event_weight(topic_events, supporting_event_ids)
        temporal_density = _driver_component_temporal_density(
            supporting_events,
            start_time=start_time,
            end_time=end_time,
        )
        entity_consistency = _driver_component_entity_consistency(supporting_events)
        external_confirmability = _driver_component_external_confirmability_proxy(supporting_events)

        score = (
            DRIVER_SCORE_WEIGHTS["supporting_event_weight"] * supporting_event_weight
            + DRIVER_SCORE_WEIGHTS["temporal_density"] * temporal_density
            + DRIVER_SCORE_WEIGHTS["entity_consistency"] * entity_consistency
            + DRIVER_SCORE_WEIGHTS["external_confirmability"] * external_confirmability
        )

        candidates.append(
            DriverCandidate(
                driver_key=driver_key,
                score=round(score, 6),
                supporting_event_ids=supporting_event_ids,
                score_components=DriverScoreComponents(
                    supporting_event_weight=round(supporting_event_weight, 6),
                    temporal_density=round(temporal_density, 6),
                    entity_consistency=round(entity_consistency, 6),
                    external_confirmability=round(external_confirmability, 6),
                ),
            )
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            -len(candidate.supporting_event_ids),
            candidate.driver_key,
        )
    )

    selected = None
    if candidates and candidates[0].score > 0.0 and candidates[0].supporting_event_ids:
        selected = candidates[0]

    return candidates, selected

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from .constants import OPPORTUNITY_TOPICS, TOPIC_SCORE_WEIGHTS
from .contracts import RankedTopicOpportunity, TopicRankingBreakdown


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _event_time(event: dict[str, Any]) -> datetime | None:
    raw = event.get("event_time") or event.get("last_updated_at")
    return raw if isinstance(raw, datetime) else None


def _impact(event: dict[str, Any]) -> float:
    raw = event.get("impact_score")
    if isinstance(raw, (int, float)):
        return _clamp01(float(raw) / 100.0)
    return 0.0


def _event_identity_key(event: dict[str, Any]) -> str:
    identity_fp = event.get("event_identity_fingerprint_v2")
    if isinstance(identity_fp, str) and identity_fp.strip():
        return f"identity:{identity_fp.strip()}"

    claim_hash = event.get("claim_hash")
    if isinstance(claim_hash, str) and claim_hash.strip():
        return f"claim:{claim_hash.strip()}"

    return f"event:{int(event.get('id') or 0)}"


def _entity_tokens(event: dict[str, Any]) -> list[str]:
    payload = event.get("latest_extraction_payload")
    tokens: list[str] = []
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

    for tag in event.get("tags") or []:
        if not isinstance(tag, dict):
            continue
        tag_value = tag.get("tag_value")
        if isinstance(tag_value, str) and tag_value.strip():
            tokens.append(f"tag:{tag_value.strip().lower()}")

    return tokens


def _relation_types(event: dict[str, Any]) -> list[str]:
    relation_types: list[str] = []
    for relation in event.get("relations") or []:
        if not isinstance(relation, dict):
            continue
        relation_type = relation.get("relation_type")
        if isinstance(relation_type, str) and relation_type.strip():
            relation_types.append(relation_type.strip().lower())
    return relation_types


def _driver_hint(event: dict[str, Any]) -> str:
    text_parts: list[str] = []
    summary = event.get("summary_1_sentence")
    if isinstance(summary, str):
        text_parts.append(summary.lower())

    payload = event.get("latest_extraction_payload")
    if isinstance(payload, dict):
        keywords = payload.get("keywords")
        if isinstance(keywords, list):
            for keyword in keywords:
                if isinstance(keyword, str):
                    text_parts.append(keyword.lower())

    text = " ".join(text_parts)
    if any(token in text for token in ("disruption", "outage", "shutdown", "restriction")):
        return "supply_disruption"
    if any(token in text for token in ("demand", "import growth", "consumption")):
        return "demand_acceleration"
    if any(token in text for token in ("inventory", "stockpile", "storage", "draw")):
        return "inventory_shift"
    if any(token in text for token in ("policy", "regulation", "sanction", "tariff", "quota")):
        return "policy_change"
    if any(token in text for token in ("shipping", "freight", "route", "spread", "repricing")):
        return "trade_flow_repricing"
    if any(token in text for token in ("weather", "storm", "freeze", "drought", "heatwave")):
        return "weather_shock"
    return "input_cost_pressure"


def _weighted_impact_sum(events: list[dict[str, Any]], *, start: datetime, end: datetime) -> float:
    span_seconds = max(1.0, (end - start).total_seconds())
    weighted = 0.0
    for event in events:
        ts = _event_time(event)
        if ts is None:
            recency_weight = 0.75
        else:
            fraction = (ts - start).total_seconds() / span_seconds
            recency_weight = 0.5 + (0.5 * _clamp01(fraction))
        weighted += _impact(event) * recency_weight
    return weighted


def _coherence_score(events: list[dict[str, Any]]) -> float:
    if not events:
        return 0.0

    entity_tokens: Counter[str] = Counter()
    relation_tokens: Counter[str] = Counter()
    driver_tokens: Counter[str] = Counter()

    for event in events:
        entity_tokens.update(_entity_tokens(event))
        relation_tokens.update(_relation_types(event))
        driver_tokens.update([_driver_hint(event)])

    entity_share = 0.0
    if entity_tokens:
        entity_share = max(entity_tokens.values()) / float(sum(entity_tokens.values()))

    relation_share = 0.0
    if relation_tokens:
        relation_share = max(relation_tokens.values()) / float(sum(relation_tokens.values()))

    driver_share = 0.0
    if driver_tokens:
        driver_share = max(driver_tokens.values()) / float(sum(driver_tokens.values()))

    return _clamp01((entity_share * 0.45) + (relation_share * 0.35) + (driver_share * 0.20))


def _actionability_score(events: list[dict[str, Any]], *, start: datetime, end: datetime) -> float:
    if not events:
        return 0.0

    avg_impact = sum(_impact(event) for event in events) / float(len(events))
    score = 0.0

    if avg_impact >= 0.65:
        score += 0.40
    elif avg_impact >= 0.50:
        score += 0.25

    if len(events) >= 3:
        score += 0.25
    elif len(events) == 2:
        score += 0.15
    else:
        score += 0.05

    relation_types = {rt for event in events for rt in _relation_types(event)}
    if relation_types & {
        "restricts_export_of",
        "curtails",
        "disrupts_logistics_of",
        "supports",
        "expands_production_of",
    }:
        score += 0.20

    recent_cutoff = end - (end - start) / 4
    recent_count = sum(1 for event in events if (_event_time(event) or start) >= recent_cutoff)
    if recent_count / float(max(1, len(events))) >= 0.40:
        score += 0.15

    return _clamp01(score)


def _novelty_score(
    current_events: list[dict[str, Any]],
    prior_events: list[dict[str, Any]],
    *,
    has_recent_memo: bool,
) -> float:
    if not current_events:
        return 0.0

    current_keys = {_event_identity_key(event) for event in current_events}
    prior_keys = {_event_identity_key(event) for event in prior_events}

    overlap_ratio = 0.0
    if current_keys:
        overlap_ratio = len(current_keys & prior_keys) / float(len(current_keys))

    novelty = _clamp01(1.0 - overlap_ratio)
    if has_recent_memo:
        novelty = _clamp01(novelty - 0.15)
    return novelty


def rank_topic_opportunities(
    *,
    current_events: list[dict[str, Any]],
    prior_events: list[dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    topic_universe: list[str] | None = None,
    limit: int = 5,
    recent_memo_topics: set[str] | None = None,
) -> list[RankedTopicOpportunity]:
    topics = list(topic_universe or OPPORTUNITY_TOPICS)
    recent_memo_topics = recent_memo_topics or set()

    by_topic_current: dict[str, list[dict[str, Any]]] = {topic: [] for topic in topics}
    by_topic_prior: dict[str, list[dict[str, Any]]] = {topic: [] for topic in topics}

    for event in current_events:
        mapped_topic = event.get("mapped_topic")
        if mapped_topic in by_topic_current:
            by_topic_current[str(mapped_topic)].append(event)

    for event in prior_events:
        mapped_topic = event.get("mapped_topic")
        if mapped_topic in by_topic_prior:
            by_topic_prior[str(mapped_topic)].append(event)

    event_count_raw = {topic: len(rows) for topic, rows in by_topic_current.items()}
    weighted_impact_raw = {
        topic: _weighted_impact_sum(rows, start=start_time, end=end_time)
        for topic, rows in by_topic_current.items()
    }
    novelty_raw = {
        topic: _novelty_score(
            by_topic_current[topic],
            by_topic_prior.get(topic, []),
            has_recent_memo=topic in recent_memo_topics,
        )
        for topic in topics
    }
    coherence_raw = {
        topic: _coherence_score(by_topic_current[topic])
        for topic in topics
    }
    actionability_raw = {
        topic: _actionability_score(by_topic_current[topic], start=start_time, end=end_time)
        for topic in topics
    }

    max_count = max(event_count_raw.values()) if event_count_raw else 0
    max_weighted_impact = max(weighted_impact_raw.values()) if weighted_impact_raw else 0.0

    ranked: list[RankedTopicOpportunity] = []
    for topic in topics:
        event_count_component = (
            event_count_raw[topic] / float(max_count) if max_count > 0 else 0.0
        )
        weighted_impact_component = (
            weighted_impact_raw[topic] / float(max_weighted_impact)
            if max_weighted_impact > 0.0
            else 0.0
        )
        novelty_component = _clamp01(novelty_raw[topic])
        coherence_component = _clamp01(coherence_raw[topic])
        actionability_component = _clamp01(actionability_raw[topic])

        topic_score = (
            TOPIC_SCORE_WEIGHTS["normalized_event_count"] * event_count_component
            + TOPIC_SCORE_WEIGHTS["normalized_weighted_impact"] * weighted_impact_component
            + TOPIC_SCORE_WEIGHTS["normalized_novelty"] * novelty_component
            + TOPIC_SCORE_WEIGHTS["normalized_coherence"] * coherence_component
            + TOPIC_SCORE_WEIGHTS["normalized_actionability"] * actionability_component
        )

        candidate_event_ids = [
            int(row["id"])
            for row in sorted(
                by_topic_current[topic],
                key=lambda row: (
                    -float(row.get("impact_score") or 0.0),
                    -((_event_time(row) or start_time).timestamp()),
                    int(row.get("id") or 0),
                ),
            )
        ]

        ranked.append(
            RankedTopicOpportunity(
                topic=topic,
                topic_score=round(topic_score, 6),
                event_count=int(event_count_raw[topic]),
                weighted_impact=round(weighted_impact_component, 6),
                novelty=round(novelty_component, 6),
                coherence=round(coherence_component, 6),
                actionability=round(actionability_component, 6),
                candidate_event_ids=candidate_event_ids[:20],
                breakdown=TopicRankingBreakdown(
                    normalized_event_count=round(event_count_component, 6),
                    normalized_weighted_impact=round(weighted_impact_component, 6),
                    normalized_novelty=round(novelty_component, 6),
                    normalized_coherence=round(coherence_component, 6),
                    normalized_actionability=round(actionability_component, 6),
                ),
            )
        )

    ranked.sort(
        key=lambda row: (
            -row.topic_score,
            -row.event_count,
            row.topic,
        )
    )

    return ranked[: max(1, limit)]


def previous_equivalent_window(*, start_time: datetime, end_time: datetime) -> tuple[datetime, datetime]:
    span = end_time - start_time
    prior_end = start_time
    prior_start = prior_end - span
    return prior_start, prior_end


def recent_same_topic_window(*, start_time: datetime, end_time: datetime) -> tuple[datetime, datetime]:
    span = end_time - start_time
    lookback = max(timedelta(hours=24), span)
    return start_time - lookback, end_time

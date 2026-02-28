from __future__ import annotations

from ..config_routing import DEFAULT_ROUTING_CONFIG, RoutingConfig
from ..schemas import ExtractionJson, RoutingDecisionData


def _priority_from_impact(impact_score: float, cfg: RoutingConfig) -> str:
    for threshold, priority in cfg.impact_priority_thresholds:
        if impact_score >= threshold:
            return priority
    return "none"


def route_extraction(
    extraction: ExtractionJson,
    cfg: RoutingConfig = DEFAULT_ROUTING_CONFIG,
    *,
    triage_action: str | None = None,
    triage_rules: list[str] | None = None,
) -> RoutingDecisionData:
    rules_fired: list[str] = []

    store_to = cfg.topic_destinations.get(extraction.topic, ["other_events"])
    rules_fired.append(f"topic_to_dest:{extraction.topic}")

    publish_priority = _priority_from_impact(extraction.impact_score, cfg)
    rules_fired.append(f"impact_to_priority:{publish_priority}")

    requires_evidence = False
    if cfg.evidence_enabled and (
        extraction.is_breaking
        or extraction.impact_score >= 60.0
        or (extraction.topic in {"macro_econ", "war_security", "credit"} and extraction.confidence >= 0.6)
    ):
        requires_evidence = True
        rules_fired.append("requires_evidence:rule_default")

    # Phase 1: build canonical events for every message with content.
    event_action = "ignore" if not extraction.summary_1_sentence else "create"
    rules_fired.append(f"event_action:{event_action}")

    flags: list[str] = []
    if requires_evidence:
        flags.append("unconfirmed")
    if extraction.impact_score >= 60.0:
        flags.append("high_impact")
    if extraction.is_breaking:
        flags.append("breaking")

    return RoutingDecisionData(
        store_to=list(store_to),
        publish_priority=publish_priority,  # type: ignore[arg-type]
        requires_evidence=requires_evidence,
        event_action=event_action,  # type: ignore[arg-type]
        triage_action=triage_action,
        triage_rules=triage_rules or [],
        flags=flags,
        rules_fired=rules_fired,
    )


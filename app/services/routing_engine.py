from __future__ import annotations

from ..config_routing import DEFAULT_ROUTING_CONFIG, RoutingConfig
from ..schemas import ExtractionJson, RoutingDecisionData


def _priority_from_impact(impact_score: float, cfg: RoutingConfig) -> str:
    for threshold, priority in cfg.impact_priority_thresholds:
        if impact_score >= threshold:
            return priority
    return "none"


def _priority_rank(priority: str) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3}.get(priority, 0)


def _priority_by_rank(rank: int) -> str:
    mapping = {0: "none", 1: "low", 2: "medium", 3: "high"}
    return mapping.get(max(0, min(3, rank)), "none")


def _cap_priority(base_priority: str, *, triage_action: str | None, local_incident: bool) -> str:
    cap_rank = 3
    if triage_action == "update":
        cap_rank = min(cap_rank, 2)
    elif triage_action == "monitor":
        cap_rank = min(cap_rank, 1)
    elif triage_action == "archive":
        cap_rank = min(cap_rank, 0)
    if local_incident:
        cap_rank = min(cap_rank, 1)
    return _priority_by_rank(min(_priority_rank(base_priority), cap_rank))


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
    local_incident = bool(triage_rules and "triage:local_incident_downgrade" in triage_rules)
    capped_priority = _cap_priority(
        publish_priority,
        triage_action=triage_action,
        local_incident=local_incident,
    )
    if capped_priority != publish_priority:
        rules_fired.append(f"triage_priority_cap:{publish_priority}->{capped_priority}")
    publish_priority = capped_priority

    requires_evidence = False
    if cfg.evidence_enabled and (
        extraction.is_breaking
        or extraction.impact_score >= 60.0
        or (extraction.topic in {"macro_econ", "war_security", "credit"} and extraction.confidence >= 0.6)
    ):
        requires_evidence = True
        rules_fired.append("requires_evidence:rule_default")
    if local_incident:
        requires_evidence = True
        rules_fired.append("requires_evidence:local_incident_override")

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
    if local_incident:
        flags.append("local_incident")

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


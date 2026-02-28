from __future__ import annotations

from dataclasses import dataclass

from ..schemas import ExtractionJson


@dataclass(frozen=True)
class TriageDecision:
    triage_action: str  # archive|monitor|update|promote
    reason_codes: list[str]


def compute_triage_action(
    extraction: ExtractionJson, *, existing_event_id: int | None = None
) -> TriageDecision:
    reasons: list[str] = []

    if existing_event_id is not None:
        reasons.append("existing_event_context")
        if extraction.impact_score >= 55.0 or extraction.is_breaking:
            reasons.append("existing_event_high_signal")
            return TriageDecision(triage_action="update", reason_codes=reasons)
        reasons.append("existing_event_low_signal")
        return TriageDecision(triage_action="monitor", reason_codes=reasons)

    if extraction.is_breaking and extraction.impact_score >= 70.0 and extraction.confidence >= 0.6:
        reasons.extend(["breaking", "high_impact", "sufficient_confidence"])
        return TriageDecision(triage_action="promote", reason_codes=reasons)

    if extraction.impact_score >= 45.0 and extraction.confidence >= 0.4:
        reasons.extend(["material_impact", "sufficient_confidence"])
        return TriageDecision(triage_action="monitor", reason_codes=reasons)

    reasons.append("low_signal")
    return TriageDecision(triage_action="archive", reason_codes=reasons)

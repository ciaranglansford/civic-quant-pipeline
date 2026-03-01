from __future__ import annotations

from dataclasses import dataclass
import re

from ..schemas import ExtractionJson


@dataclass(frozen=True)
class TriageDecision:
    triage_action: str  # archive|monitor|update|promote
    reason_codes: list[str]


@dataclass(frozen=True)
class CandidateEventContext:
    impact_band: str | None = None
    entities: set[str] | None = None
    summary_tags: set[str] | None = None
    source_class: str | None = None


@dataclass(frozen=True)
class TriageContext:
    existing_event_id: int | None = None
    candidate_event: CandidateEventContext | None = None
    soft_related_match: bool = False
    burst_low_delta_prior_count: int = 0


_REACTION_LEXICON = (
    "condemn",
    "concern",
    "urge",
    "calls for",
    "unacceptable",
    "warns",
    "responds",
)
_OPERATIONAL_LEXICON = (
    "strike",
    "attacked",
    "launched",
    "killed",
    "injured",
    "casualties",
    "missile",
    "troops",
    "explosion",
)
_LOCAL_INCIDENT_LEXICON = (
    "police",
    "incident",
    "injured",
    "city",
    "county",
    "sheriff",
    "public safety",
)
_ATTRIBUTION_AUTHORITY_MARKERS = (
    "police",
    "ministry",
    "official",
    "military",
    "agency",
    "spokesperson",
    "according to",
)
_COMMENTARY_MARKERS = (
    "commentary",
    "analyst",
    "opinion",
    "urges",
    "condemns",
    "concerned",
)
_CONFLICT_GEO_MARKERS = (
    "missile",
    "strike",
    "military",
    "airstrike",
    "drone",
    "cross-border",
    "invasion",
    "army",
    "navy",
    "tehran",
    "israel",
    "iran",
    "ukraine",
    "russia",
)
_WS_RE = re.compile(r"\s+")
_LOCAL_GEO_RE = re.compile(r"\b[A-Z][a-z]+,\s*[A-Z]{2}\b")


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WS_RE.sub(" ", value.strip()).lower()


def _keyword_set(extraction: ExtractionJson) -> list[str]:
    cleaned: set[str] = set()
    for keyword in extraction.keywords:
        token = _normalize_text(keyword)
        if token:
            cleaned.add(token)
    return sorted(cleaned)


def _summary_tags(summary: str) -> set[str]:
    normalized = _normalize_text(summary)
    tags: set[str] = set()
    if any(token in normalized for token in _REACTION_LEXICON):
        tags.add("reaction")
    if any(token in normalized for token in _OPERATIONAL_LEXICON):
        tags.add("operational")
    if any(token in normalized for token in _LOCAL_INCIDENT_LEXICON):
        tags.add("local_incident")
    return tags


def classify_source(source_claimed: str | None, summary: str) -> str:
    source = _normalize_text(source_claimed)
    summary_norm = _normalize_text(summary)
    if any(marker in source for marker in _ATTRIBUTION_AUTHORITY_MARKERS if marker != "according to"):
        return "authority"
    if "according to" in summary_norm:
        return "authority"
    combined = f"{source} {summary_norm}".strip()
    if any(marker in combined for marker in _COMMENTARY_MARKERS):
        return "commentary"
    return "unknown"


def derive_claim_signature(extraction: ExtractionJson) -> str:
    tags = ",".join(sorted(_summary_tags(extraction.summary_1_sentence)))
    keywords = ",".join(_keyword_set(extraction))
    source = _normalize_text(extraction.source_claimed)
    return f"{extraction.topic}|{keywords}|{source}|{tags}"


def impact_band(score: float) -> str:
    if score >= 85.0:
        return "critical"
    if score >= 70.0:
        return "high"
    if score >= 55.0:
        return "medium"
    return "low"


def confidence_band(score: float) -> str:
    if score >= 0.85:
        return "strong"
    if score >= 0.75:
        return "usable"
    return "weak"


def _band_rank(name: str) -> int:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return order.get(name, -1)


def entity_signature(extraction: ExtractionJson) -> set[str]:
    out: set[str] = set()
    for value in extraction.entities.countries:
        if value:
            out.add(f"country:{_normalize_text(value)}")
    for value in extraction.entities.orgs:
        if value:
            out.add(f"org:{_normalize_text(value)}")
    for value in extraction.entities.people:
        if value:
            out.add(f"person:{_normalize_text(value)}")
    return out


def soft_related_overlap_count(extraction: ExtractionJson, candidate_entities: set[str]) -> int:
    if not candidate_entities:
        return 0
    return len(entity_signature(extraction) & candidate_entities)


def is_local_domestic_incident(extraction: ExtractionJson) -> bool:
    summary = extraction.summary_1_sentence or ""
    source = extraction.source_claimed or ""
    combined = f"{summary} {' '.join(extraction.keywords)} {source}"
    normalized = _normalize_text(combined)
    has_local_authority = any(token in normalized for token in ("police", "sheriff", "public safety"))
    has_incident_language = any(token in normalized for token in ("incident", "injured", "wounded", "casualt"))
    has_local_geo = bool(_LOCAL_GEO_RE.search(summary)) or any(
        token in normalized for token in (" city ", " county ", " state ")
    )
    has_conflict_marker = any(token in normalized for token in _CONFLICT_GEO_MARKERS)
    return has_local_authority and has_incident_language and (has_local_geo or "police" in normalized) and not has_conflict_marker


def _materially_new(
    extraction: ExtractionJson,
    *,
    candidate: CandidateEventContext | None,
) -> bool:
    if candidate is None:
        return True

    current_entities = entity_signature(extraction)
    candidate_entities = candidate.entities or set()
    new_entities = bool(current_entities - candidate_entities)
    if new_entities:
        return True

    current_band = impact_band(extraction.impact_score)
    if candidate.impact_band is not None and _band_rank(current_band) > _band_rank(candidate.impact_band):
        return True

    current_tags = _summary_tags(extraction.summary_1_sentence)
    candidate_tags = candidate.summary_tags or set()
    reaction_to_operational = "operational" in current_tags and "operational" not in candidate_tags and "reaction" in candidate_tags
    if reaction_to_operational:
        return True

    current_source_class = classify_source(extraction.source_claimed, extraction.summary_1_sentence)
    if candidate.source_class == "commentary" and current_source_class == "authority":
        return True

    return False


def compute_triage_action(
    extraction: ExtractionJson,
    *,
    existing_event_id: int | None = None,
    context: TriageContext | None = None,
) -> TriageDecision:
    if context is None:
        context = TriageContext(existing_event_id=existing_event_id)
    elif existing_event_id is not None and context.existing_event_id is None:
        context = TriageContext(
            existing_event_id=existing_event_id,
            candidate_event=context.candidate_event,
            soft_related_match=context.soft_related_match,
            burst_low_delta_prior_count=context.burst_low_delta_prior_count,
        )

    reasons: list[str] = []
    impact = impact_band(extraction.impact_score)
    conf = confidence_band(extraction.confidence)
    reasons.append(f"triage:score_band:{impact}")
    reasons.append(f"triage:confidence_band:{conf}")

    local_incident = is_local_domestic_incident(extraction)
    if local_incident:
        reasons.append("triage:local_incident_downgrade")

    novelty_state = "new_event" if context.existing_event_id is None else "related_update"
    materially_new = _materially_new(extraction, candidate=context.candidate_event)

    if context.existing_event_id is not None and not materially_new:
        novelty_state = "repeat_low_delta"
        reasons.append("triage:repeat_downgrade")

    if context.soft_related_match:
        reasons.append("triage:soft_related_match")

    # Prevent over-promotion for soft-related low-delta messages even when fingerprint changes.
    if context.existing_event_id is None and context.soft_related_match and not materially_new:
        reasons.append("triage:soft_related_downgrade")
        novelty_state = "repeat_low_delta"

    if conf == "weak" and impact == "low":
        reasons.append("triage:low_signal_archive")
        action = "archive"
    elif novelty_state == "new_event" and impact in {"high", "critical"} and conf in {"usable", "strong"}:
        reasons.append("triage:new_event_promote")
        action = "promote"
    elif novelty_state == "related_update" and materially_new:
        reasons.append("triage:related_material_update")
        action = "update"
    elif novelty_state in {"related_update", "repeat_low_delta"}:
        action = "monitor"
    else:
        action = "monitor"

    # Strong burst suppression: cap second+ low-delta variants.
    if novelty_state == "repeat_low_delta":
        if context.burst_low_delta_prior_count >= 2:
            reasons.append("triage:burst_cap_monitor")
            action = "monitor"
        elif context.burst_low_delta_prior_count >= 1:
            reasons.append("triage:burst_cap_update")
            action = "update"

    # Local incident gate: never allow top urgency for noisy domestic incidents.
    if local_incident and action in {"promote", "update"}:
        action = "monitor"

    return TriageDecision(triage_action=action, reason_codes=reasons)

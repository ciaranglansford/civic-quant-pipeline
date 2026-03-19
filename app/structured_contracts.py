from __future__ import annotations

from dataclasses import dataclass


# Keep the controlled vocabulary intentionally compact for this MVP.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "policy",
        "conflict",
        "logistics",
        "production",
        "sanctions",
        "spending",
        "weather",
        "market",
        "company",
        "other",
    }
)

DIRECTIONALITY_VALUES: frozenset[str] = frozenset({"stress", "easing", "neutral"})
TAG_SOURCES: frozenset[str] = frozenset({"observed", "inferred"})
RELATION_SOURCES: frozenset[str] = TAG_SOURCES
ENRICHMENT_ROUTES: frozenset[str] = frozenset({"store_only", "index_only", "deep_enrich"})

TAG_FAMILIES: frozenset[str] = frozenset(
    {
        "countries",
        "companies",
        "commodities",
        "sectors",
        "event_mechanisms",
        "policy",
        "conflict",
        "logistics",
        "production",
        "sanctions",
        "spending",
        "weather",
        "strategic",
        "directionality",
    }
)

RELATION_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "country",
        "company",
        "commodity",
        "sector",
        "state",
        "policy",
        "conflict",
        "logistics",
        "production",
        "sanctions",
        "spending",
        "weather",
    }
)

RELATION_TYPES: frozenset[str] = frozenset(
    {
        "conflict_with",
        "restricts_export_of",
        "curtails",
        "input_to",
        "increases_spending_on",
        "sanctions",
        "disrupts_logistics_of",
        "expands_production_of",
        "supports",
        "contradicts",
    }
)

_TAG_FAMILY_ALIASES = {
    "country": "countries",
    "company": "companies",
    "commodity": "commodities",
    "sector": "sectors",
    "event_mechanism": "event_mechanisms",
    "mechanism": "event_mechanisms",
}

_RELATION_ENTITY_TYPE_ALIASES = {
    "org": "company",
    "organization": "company",
    "country": "country",
    "commodity": "commodity",
    "sector": "sector",
    "company": "company",
    "state": "state",
}


@dataclass(frozen=True)
class StructuredNormalizationReport:
    dropped_tags: int = 0
    dropped_relations: int = 0


def _normalize_key(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def normalize_event_type(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    return normalized if normalized in EVENT_TYPES else None


def normalize_directionality(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    return normalized if normalized in DIRECTIONALITY_VALUES else None


def normalize_tag_family(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    normalized = _TAG_FAMILY_ALIASES.get(normalized, normalized)
    return normalized if normalized in TAG_FAMILIES else None


def normalize_tag_source(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    return normalized if normalized in TAG_SOURCES else None


def normalize_relation_source(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    return normalized if normalized in RELATION_SOURCES else None


def normalize_relation_type(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    return normalized if normalized in RELATION_TYPES else None


def normalize_relation_entity_type(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    normalized = _RELATION_ENTITY_TYPE_ALIASES.get(normalized, normalized)
    return normalized if normalized in RELATION_ENTITY_TYPES else None


def normalize_tag_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def normalize_relation_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def normalize_enrichment_route(value: str | None) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    return normalized if normalized in ENRICHMENT_ROUTES else None


def inference_level_for_source(source: str) -> int:
    return 1 if source == "inferred" else 0


def is_strategic_tag(tag_type: str) -> bool:
    return tag_type == "strategic"

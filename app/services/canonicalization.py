from __future__ import annotations

import copy
import re
from collections.abc import Iterable

from ..schemas import ExtractionJson


_WS_RE = re.compile(r"\s+")
_TICKER_CLEAN_RE = re.compile(r"[^A-Z0-9.\-]")
_PRONOUN_RE = re.compile(r"\b(it|they|he|she)\b", re.IGNORECASE)
_HIGH_RISK_TERMS = (
    "killing",
    "killed",
    "assassination",
    "death of",
    "strike",
    "attack",
    "attacked",
    "targeting",
    "casualties",
    "injured",
    "wounded",
    "dead",
    "invasion",
    "military escalation",
    "direct strike",
    "major incident",
    "launched",
    "missile",
    "missiles",
)
_ATTRIBUTION_MARKERS = (
    "according to",
    "said",
    "says",
    "reported",
    "reportedly",
    "claims",
    "claimed",
    "responded to reports",
)

_COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States",
    "u.s.": "United States",
    "u.s": "United States",
    "usa": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "u.k": "United Kingdom",
    "uae": "United Arab Emirates",
    "eu": "European Union",
}


def _normalize_spaces(value: str) -> str:
    return _WS_RE.sub(" ", value.strip())


def _canonical_country(value: str) -> str:
    cleaned = _normalize_spaces(value)
    if not cleaned:
        return ""
    alias_key = cleaned.lower()
    canonical = _COUNTRY_ALIASES.get(alias_key, cleaned)
    return canonical.title() if canonical.islower() else canonical


def _canonical_countries(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        canonical = _canonical_country(raw)
        if not canonical:
            continue
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)
    return sorted(out, key=str.lower)


def _canonical_tickers(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _normalize_spaces(raw).upper()
        cleaned = _TICKER_CLEAN_RE.sub("", cleaned)
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return sorted(out)


def _canonical_text_list(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _normalize_spaces(raw)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return sorted(out, key=str.lower)


def _canonical_source(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _normalize_spaces(value)
    return cleaned or None


def _canonicalize_fingerprint_country_component(fingerprint: str, countries: list[str]) -> str:
    parts = fingerprint.split("|")
    if len(parts) < 8:
        return fingerprint
    parts[2] = ",".join(countries)
    return "|".join(parts)


def _summary_has_high_risk_language(summary: str) -> bool:
    normalized = _normalize_spaces(summary).lower()
    return any(token in normalized for token in _HIGH_RISK_TERMS)


def _summary_has_attribution(summary: str) -> bool:
    normalized = _normalize_spaces(summary).lower()
    return any(token in normalized for token in _ATTRIBUTION_MARKERS)


def _best_actor(canonical_payload: dict) -> str | None:
    source = canonical_payload.get("source_claimed")
    if isinstance(source, str) and source.strip():
        return _normalize_spaces(source)
    entities = canonical_payload.get("entities") or {}
    for key in ("orgs", "people", "countries"):
        values = entities.get(key, [])
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    return _normalize_spaces(value)
    return None


def _rewrite_summary_safely(canonical_payload: dict) -> tuple[str, list[str]]:
    summary_raw = str(canonical_payload.get("summary_1_sentence") or "")
    summary = _normalize_spaces(summary_raw)
    rules: list[str] = []
    if not summary:
        return summary_raw, rules

    actor = _best_actor(canonical_payload)
    if _PRONOUN_RE.search(summary):
        if actor:
            summary = _PRONOUN_RE.sub(actor, summary, count=1)
            rules.append("summary_pronoun_disambiguated")

    if _summary_has_high_risk_language(summary) and not _summary_has_attribution(summary):
        claim = summary.rstrip(".")
        if actor:
            summary = f"{actor} said {claim.lower()}."
        else:
            summary = f"Reportedly, {claim.lower()}."
        rules.append("summary_high_risk_attribution_rewrite")

    return summary, rules


def canonicalize_extraction(payload: dict) -> tuple[ExtractionJson, list[str]]:
    """
    Deterministically canonicalize validated extraction payload values for downstream logic.
    Returns a validated ExtractionJson and fired canonicalization rule identifiers.
    """
    canonical_payload = copy.deepcopy(payload)
    rules: list[str] = []

    entities = canonical_payload.setdefault("entities", {})

    canonical_countries = _canonical_countries(entities.get("countries", []))
    if canonical_countries != entities.get("countries", []):
        rules.append("country_alias_normalization")
    entities["countries"] = canonical_countries

    affected = _canonical_countries(canonical_payload.get("affected_countries_first_order", []))
    if affected != canonical_payload.get("affected_countries_first_order", []):
        rules.append("affected_country_alias_normalization")
    canonical_payload["affected_countries_first_order"] = affected

    tickers = _canonical_tickers(entities.get("tickers", []))
    if tickers != entities.get("tickers", []):
        rules.append("ticker_normalization")
    entities["tickers"] = tickers

    orgs = _canonical_text_list(entities.get("orgs", []))
    if orgs != entities.get("orgs", []):
        rules.append("org_text_normalization")
    entities["orgs"] = orgs

    people = _canonical_text_list(entities.get("people", []))
    if people != entities.get("people", []):
        rules.append("person_text_normalization")
    entities["people"] = people

    source_claimed = _canonical_source(canonical_payload.get("source_claimed"))
    if source_claimed != canonical_payload.get("source_claimed"):
        rules.append("source_text_normalization")
    canonical_payload["source_claimed"] = source_claimed

    summary, summary_rules = _rewrite_summary_safely(canonical_payload)
    if summary != canonical_payload.get("summary_1_sentence"):
        rules.extend(summary_rules)
    canonical_payload["summary_1_sentence"] = summary

    fingerprint = str(canonical_payload.get("event_fingerprint") or "")
    canonical_fingerprint = _canonicalize_fingerprint_country_component(fingerprint, canonical_countries)
    if canonical_fingerprint != fingerprint:
        rules.append("event_fingerprint_country_normalization")
    canonical_payload["event_fingerprint"] = canonical_fingerprint

    return ExtractionJson.model_validate(canonical_payload), rules

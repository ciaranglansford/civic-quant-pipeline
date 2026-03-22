from __future__ import annotations

import re
from typing import Iterable

from .constants import (
    OPTIONAL_LIGHT_TRACEABILITY_SECTION_KEYS,
    TOPIC_KEYWORDS,
    TRACEABILITY_REQUIRED_SECTION_KEYS,
)
from .contracts import (
    ExternalEvidencePack,
    MemoValidationIssue,
    MemoValidationResult,
    OpportunityMemoInputPack,
    OpportunityMemoStructuredArtifact,
)


_NUMERIC_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
_GENERIC_TARGET_PHRASES = {
    "shipping industry",
    "energy markets",
    "commodity sector",
    "commodities sector",
    "energy sector",
    "global markets",
}
_TARGET_SPECIFICITY_TOKENS = (
    "spread",
    "basis",
    "curve",
    "corridor",
    "route",
    "benchmark",
    "ttf",
    "henry hub",
    "brent",
    "wti",
    "freight",
    "producer",
    "import",
    "export",
    "class",
    "bucket",
    "equities",
    "futures",
    "options",
    "volatility",
)
_THESIS_DIRECTION_TOKENS = (
    "repricing",
    "tightening",
    "widening",
    "upside",
    "downside",
    "overweight",
    "underweight",
    "long",
    "short",
    "premium",
    "discount",
    "bullish",
    "bearish",
)
_THESIS_REASON_TOKENS = (
    "driven by",
    "because",
    "as",
    "due to",
    "from",
    "on",
)
_TIMING_TOKENS = (
    "now",
    "recent",
    "within",
    "window",
    "this week",
    "last",
    "currently",
    "immediate",
    "accelerat",
)
_TRADE_EXPRESSION_TOKENS = (
    "futures",
    "options",
    "spread",
    "basis",
    "curve",
    "pair trade",
    "overweight",
    "underweight",
    "long",
    "short",
    "hedge",
    "exposure",
    "freight",
    "benchmark",
    "volatility",
)
_VAGUE_TRADE_PHRASES = (
    "monitor developments",
    "consider diversifying",
    "proactive approach",
    "investors may benefit",
    "keep watching",
)
_OPPORTUNITY_LOGIC_TOKENS = (
    "mispriced",
    "underappreciated",
    "repricing",
    "risk premium",
    "spread",
    "transmission",
    "valuation",
    "margin",
    "earnings",
    "cash flow",
    "asymmetry",
    "discount",
    "financially",
)
_FILLER_LIST_PHRASES = (
    "monitor developments",
    "stay informed",
    "various factors",
    "market uncertainty",
    "dynamic environment",
)


def _is_non_empty_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _word_count(text: str) -> int:
    return len([token for token in text.strip().split() if token.strip()])


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _keyword_present(*, text: str, keyword: str) -> bool:
    escaped = re.escape(keyword.lower())
    pattern = rf"(?<!\w){escaped}(?!\w)"
    return re.search(pattern, text) is not None


def _traceability_map(memo: OpportunityMemoStructuredArtifact) -> dict[str, tuple[list[int], list[str]]]:
    mapping: dict[str, tuple[list[int], list[str]]] = {}
    for row in memo.traceability.paragraph_sources:
        mapping[row.paragraph_key] = (list(row.internal_event_ids), list(row.external_source_ids))
    return mapping


def _required_traceability_keys(memo: OpportunityMemoStructuredArtifact) -> list[str]:
    keys: list[str] = [
        "core_thesis_one_liner",
        "market_setup",
        "background",
        "primary_driver",
        "why_now",
        "why_this_is_an_opportunity",
        "trade_expression",
        "conclusion",
    ]
    keys.extend([f"supporting_developments[{idx}]" for idx in range(len(memo.supporting_developments))])
    keys.extend([f"quantified_evidence_points[{idx}]" for idx in range(len(memo.quantified_evidence_points))])
    keys.extend([f"risks[{idx}]" for idx in range(len(memo.risks))])
    keys.extend([f"invalidation_triggers[{idx}]" for idx in range(len(memo.invalidation_triggers))])
    keys.extend([f"watchpoints[{idx}]" for idx in range(len(memo.watchpoints))])
    return keys


def _iter_all_evidence_text(memo: OpportunityMemoStructuredArtifact) -> Iterable[str]:
    for section_key in TRACEABILITY_REQUIRED_SECTION_KEYS | OPTIONAL_LIGHT_TRACEABILITY_SECTION_KEYS:
        value = getattr(memo, section_key, None)
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, str):
                    yield row


def _topic_drift_detected(*, topic: str, memo: OpportunityMemoStructuredArtifact) -> bool:
    all_text = " ".join(_normalize(value) for value in _iter_all_evidence_text(memo))
    if not all_text:
        return False

    selected_topic_hits = sum(
        1 for keyword in TOPIC_KEYWORDS.get(topic, ()) if _keyword_present(text=all_text, keyword=keyword)
    )
    strongest_other_hits = 0
    total_other_hits = 0
    other_topics_nonzero = 0
    other_topics_ge2 = 0
    for other_topic, keywords in TOPIC_KEYWORDS.items():
        if other_topic == topic:
            continue
        hit_count = sum(1 for keyword in keywords if _keyword_present(text=all_text, keyword=keyword))
        if hit_count > 0:
            other_topics_nonzero += 1
        if hit_count >= 2:
            other_topics_ge2 += 1
        strongest_other_hits = max(strongest_other_hits, hit_count)
        total_other_hits += hit_count

    if total_other_hits == 0:
        return False
    if selected_topic_hits == 0:
        return strongest_other_hits >= 2
    if selected_topic_hits == 1:
        return strongest_other_hits >= 3 and total_other_hits >= 3
    return (
        other_topics_ge2 >= 2 and total_other_hits >= (selected_topic_hits + 3)
    ) or (
        strongest_other_hits >= 4 and total_other_hits >= (selected_topic_hits + 4)
    )


def _target_is_too_generic(*, opportunity_target: str, topic: str) -> bool:
    normalized = _normalize(opportunity_target)
    if _word_count(normalized) < 3:
        return True
    if normalized in _GENERIC_TARGET_PHRASES:
        return True
    if any(phrase in normalized for phrase in _GENERIC_TARGET_PHRASES):
        if not any(token in normalized for token in _TARGET_SPECIFICITY_TOKENS):
            return True
    topic_tokens = TOPIC_KEYWORDS.get(topic, ())
    has_topic_specificity = any(token in normalized for token in topic_tokens)
    has_specificity_token = any(token in normalized for token in _TARGET_SPECIFICITY_TOKENS) or has_topic_specificity
    has_numeric_anchor = bool(_NUMERIC_PATTERN.search(normalized))
    if not has_specificity_token and not has_numeric_anchor:
        return True
    return False


def _thesis_is_weak(*, thesis: str, input_pack: OpportunityMemoInputPack) -> bool:
    normalized = _normalize(thesis)
    if _word_count(normalized) < 12:
        return True
    has_direction = any(token in normalized for token in _THESIS_DIRECTION_TOKENS)
    has_reason = any(token in normalized for token in _THESIS_REASON_TOKENS)
    topic_tokens = TOPIC_KEYWORDS.get(input_pack.topic, ())
    has_topic_anchor = any(token in normalized for token in topic_tokens)
    driver_key = (
        input_pack.selected_primary_driver.driver_key.replace("_", " ")
        if input_pack.selected_primary_driver is not None
        else ""
    )
    has_driver_anchor = bool(driver_key and driver_key in normalized)
    return not (has_direction and has_reason and (has_topic_anchor or has_driver_anchor))


def _why_now_is_generic(why_now: str) -> bool:
    normalized = _normalize(why_now)
    if _word_count(normalized) < 12:
        return True
    has_timing_token = any(token in normalized for token in _TIMING_TOKENS) or bool(_NUMERIC_PATTERN.search(normalized))
    return not has_timing_token


def _trade_expression_is_vague(trade_expression: str) -> bool:
    normalized = _normalize(trade_expression)
    if _word_count(normalized) < 12:
        return True
    if any(phrase in normalized for phrase in _VAGUE_TRADE_PHRASES):
        return True
    has_expression_route = any(token in normalized for token in _TRADE_EXPRESSION_TOKENS)
    return not has_expression_route


def _opportunity_framing_is_generic(why_opportunity: str) -> bool:
    normalized = _normalize(why_opportunity)
    if _word_count(normalized) < 14:
        return True
    has_financial_logic = any(token in normalized for token in _OPPORTUNITY_LOGIC_TOKENS)
    return not has_financial_logic


def _count_quantitative_points(points: list[str]) -> int:
    quantitative = 0
    for row in points:
        normalized = _normalize(row)
        if _NUMERIC_PATTERN.search(normalized):
            quantitative += 1
    return quantitative


def _list_section_has_filler(values: list[str]) -> bool:
    for row in values:
        normalized = _normalize(row)
        if _word_count(normalized) < 5:
            return True
        if any(phrase in normalized for phrase in _FILLER_LIST_PHRASES):
            return True
    return False


def validate_opportunity_memo(
    *,
    memo: OpportunityMemoStructuredArtifact,
    input_pack: OpportunityMemoInputPack,
    external_evidence: ExternalEvidencePack,
    min_supporting_events: int,
    min_external_sources: int,
    topic_selection_threshold: float,
) -> MemoValidationResult:
    errors: list[MemoValidationIssue] = []
    warnings: list[MemoValidationIssue] = []

    if len(input_pack.selected_event_ids) < max(1, min_supporting_events):
        errors.append(
            MemoValidationIssue(
                code="insufficient_supporting_events",
                message=f"Selected topic has fewer than {min_supporting_events} supporting events.",
            )
        )

    if input_pack.selected_primary_driver is None:
        errors.append(
            MemoValidationIssue(
                code="missing_primary_driver",
                message="No primary driver was selected for the memo topic.",
            )
        )

    if len(external_evidence.sources) < max(1, min_external_sources):
        errors.append(
            MemoValidationIssue(
                code="insufficient_external_sources",
                message=f"External evidence source count is below {min_external_sources}.",
            )
        )

    required_string_sections = [
        "title",
        "core_thesis_one_liner",
        "opportunity_target",
        "market_setup",
        "background",
        "primary_driver",
        "why_now",
        "why_this_is_an_opportunity",
        "trade_expression",
        "conclusion",
    ]
    for section_key in required_string_sections:
        if not _is_non_empty_text(getattr(memo, section_key, None)):
            errors.append(
                MemoValidationIssue(
                    code="missing_required_section",
                    message=f"Required section '{section_key}' is empty.",
                )
            )

    if memo.confidence_level not in {"low", "medium", "high"}:
        errors.append(
            MemoValidationIssue(
                code="invalid_confidence_level",
                message="confidence_level must be one of: low, medium, high.",
            )
        )

    list_constraints = {
        "supporting_developments": (2, 4),
        "quantified_evidence_points": (2, 20),
        "risks": (2, 20),
        "invalidation_triggers": (2, 20),
        "watchpoints": (2, 20),
    }
    for section_key, (minimum, maximum) in list_constraints.items():
        section_values = getattr(memo, section_key, None)
        if not isinstance(section_values, list):
            errors.append(
                MemoValidationIssue(
                    code="missing_required_section",
                    message=f"Required section '{section_key}' is empty.",
                )
            )
            continue
        if len(section_values) < minimum:
            errors.append(
                MemoValidationIssue(
                    code="insufficient_list_items",
                    message=f"Section '{section_key}' must contain at least {minimum} items.",
                )
            )
        if len(section_values) > maximum:
            errors.append(
                MemoValidationIssue(
                    code="excessive_list_items",
                    message=f"Section '{section_key}' must contain at most {maximum} items.",
                )
            )
        if any(not _is_non_empty_text(value if isinstance(value, str) else None) for value in section_values):
            errors.append(
                MemoValidationIssue(
                    code="missing_required_section",
                    message=f"Required section '{section_key}' has an empty item.",
                )
            )
        if isinstance(section_values, list) and _list_section_has_filler([str(value) for value in section_values]):
            errors.append(
                MemoValidationIssue(
                    code="filler_list_content",
                    message=f"Section '{section_key}' contains filler or overly generic items.",
                )
            )

    quantitative_count = _count_quantitative_points(memo.quantified_evidence_points)
    if quantitative_count < 2:
        errors.append(
            MemoValidationIssue(
                code="insufficient_quantified_evidence",
                message="quantified_evidence_points must contain at least 2 quantitative points.",
            )
        )

    if _target_is_too_generic(opportunity_target=memo.opportunity_target, topic=input_pack.topic):
        errors.append(
            MemoValidationIssue(
                code="generic_opportunity_target",
                message="opportunity_target is too generic; provide a narrower exposure definition.",
            )
        )

    if _thesis_is_weak(thesis=memo.core_thesis_one_liner, input_pack=input_pack):
        errors.append(
            MemoValidationIssue(
                code="weak_core_thesis",
                message="core_thesis_one_liner must state setup, direction/opportunity, and driver logic.",
            )
        )

    if _why_now_is_generic(memo.why_now):
        errors.append(
            MemoValidationIssue(
                code="generic_why_now",
                message="why_now must be tied to timing and recent-window developments.",
            )
        )

    if _trade_expression_is_vague(memo.trade_expression):
        errors.append(
            MemoValidationIssue(
                code="vague_trade_expression",
                message="trade_expression must name a concrete exposure route.",
            )
        )

    if _opportunity_framing_is_generic(memo.why_this_is_an_opportunity):
        errors.append(
            MemoValidationIssue(
                code="generic_opportunity_framing",
                message="why_this_is_an_opportunity must explain financial actionability.",
            )
        )

    traceability = _traceability_map(memo)
    allowed_internal_ids = set(input_pack.selected_event_ids)
    allowed_external_ids = {source.source_id for source in external_evidence.sources}
    for paragraph_key in _required_traceability_keys(memo):
        pair = traceability.get(paragraph_key)
        if pair is None:
            errors.append(
                MemoValidationIssue(
                    code="missing_traceability",
                    message=f"Missing traceability for paragraph '{paragraph_key}'.",
                )
            )
            continue

        internal_event_ids, external_source_ids = pair
        if not internal_event_ids or not external_source_ids:
            errors.append(
                MemoValidationIssue(
                    code="missing_traceability",
                    message=f"Traceability for paragraph '{paragraph_key}' must include internal and external sources.",
                )
            )
            continue

        if any(event_id not in allowed_internal_ids for event_id in internal_event_ids):
            errors.append(
                MemoValidationIssue(
                    code="invalid_traceability_internal_event_id",
                    message=f"Traceability paragraph '{paragraph_key}' includes unknown internal event ids.",
                )
            )
        if any(source_id not in allowed_external_ids for source_id in external_source_ids):
            errors.append(
                MemoValidationIssue(
                    code="invalid_traceability_external_source_id",
                    message=f"Traceability paragraph '{paragraph_key}' includes unknown external source ids.",
                )
            )

    if _topic_drift_detected(topic=input_pack.topic, memo=memo):
        errors.append(
            MemoValidationIssue(
                code="topic_drift_detected",
                message="Memo appears to drift across multiple unrelated topics.",
            )
        )

    unique_publishers = {
        source.publisher.strip().lower()
        for source in external_evidence.sources
        if isinstance(source.publisher, str) and source.publisher.strip()
    }
    if len(unique_publishers) < 2 and len(external_evidence.sources) >= 1:
        warnings.append(
            MemoValidationIssue(
                code="weak_source_diversity",
                message="External evidence source diversity is lower than ideal.",
            )
        )

    if input_pack.selection_diagnostics.topic_score <= (topic_selection_threshold + 0.03):
        warnings.append(
            MemoValidationIssue(
                code="novelty_or_selection_borderline",
                message="Topic score is close to threshold; novelty/conviction may be borderline.",
            )
        )

    if memo.confidence_level == "high" and quantitative_count < 3:
        warnings.append(
            MemoValidationIssue(
                code="confidence_evidence_mismatch",
                message="High confidence with limited quantitative evidence may be overstated.",
            )
        )

    return MemoValidationResult(ok=not errors, errors=errors, warnings=warnings)

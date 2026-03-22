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
        "thesis",
        "background",
        "primary_driver",
        "why_now",
        "action_path",
        "conclusion",
    ]
    keys.extend([f"supporting_developments[{idx}]" for idx in range(len(memo.supporting_developments))])
    keys.extend([f"risks[{idx}]" for idx in range(len(memo.risks))])
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
    for other_topic, keywords in TOPIC_KEYWORDS.items():
        if other_topic == topic:
            continue
        hit_count = sum(1 for keyword in keywords if _keyword_present(text=all_text, keyword=keyword))
        if hit_count > 0:
            other_topics_nonzero += 1
        strongest_other_hits = max(strongest_other_hits, hit_count)
        total_other_hits += hit_count

    if total_other_hits == 0:
        return False
    if selected_topic_hits == 0:
        return strongest_other_hits >= 2
    if selected_topic_hits == 1:
        return strongest_other_hits >= 3 or (other_topics_nonzero >= 2 and total_other_hits >= 3)
    return total_other_hits >= (selected_topic_hits + 2) and (
        strongest_other_hits >= 2 or other_topics_nonzero >= 2
    )


def _action_path_is_vague(action_path: str) -> bool:
    normalized = _normalize(action_path)
    if _word_count(normalized) < 14:
        return True

    action_verbs = (
        "allocate",
        "overweight",
        "underweight",
        "hedge",
        "position",
        "buy",
        "sell",
        "rebalance",
        "monitor",
        "spread",
        "futures",
        "options",
        "exposure",
    )
    return not any(token in normalized for token in action_verbs)


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
        "thesis",
        "opportunity_target",
        "background",
        "primary_driver",
        "why_now",
        "action_path",
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

    required_list_sections = [
        "supporting_developments",
        "risks",
        "watchpoints",
    ]
    for section_key in required_list_sections:
        section_values = getattr(memo, section_key, None)
        if not isinstance(section_values, list) or not section_values:
            errors.append(
                MemoValidationIssue(
                    code="missing_required_section",
                    message=f"Required section '{section_key}' is empty.",
                )
            )
            continue
        if any(not _is_non_empty_text(value if isinstance(value, str) else None) for value in section_values):
            errors.append(
                MemoValidationIssue(
                    code="missing_required_section",
                    message=f"Required section '{section_key}' has an empty item.",
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

    opportunity_target_trace = traceability.get("opportunity_target")
    if _word_count(memo.opportunity_target) >= 18 and opportunity_target_trace is None:
        errors.append(
            MemoValidationIssue(
                code="missing_traceability",
                message="Opportunity target is long-form and requires traceability support.",
            )
        )

    if _topic_drift_detected(topic=input_pack.topic, memo=memo):
        errors.append(
            MemoValidationIssue(
                code="topic_drift_detected",
                message="Memo appears to drift across multiple unrelated topics.",
            )
        )

    if _action_path_is_vague(memo.action_path):
        errors.append(
            MemoValidationIssue(
                code="action_path_too_vague",
                message="Action path is too vague to be operationally useful.",
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

    risk_text = " ".join(_normalize(value) for value in memo.risks)
    if "offset" not in risk_text and "contradict" not in risk_text and "invalidate" not in risk_text:
        warnings.append(
            MemoValidationIssue(
                code="contradiction_handling_partial",
                message="Risk section does not explicitly discuss contradiction/offset handling.",
            )
        )

    return MemoValidationResult(ok=not errors, errors=errors, warnings=warnings)

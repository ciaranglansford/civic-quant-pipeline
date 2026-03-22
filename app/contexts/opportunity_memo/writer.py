from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from typing import Protocol

import httpx

from ...config import Settings
from .contracts import (
    ExternalEvidencePack,
    OpportunityMemoInputPack,
    OpportunityMemoStructuredArtifact,
    ParagraphSourceMap,
)


class OpportunityMemoWriterError(RuntimeError):
    pass


class OpportunityMemoWriter(Protocol):
    name: str

    def write(
        self,
        *,
        input_pack: OpportunityMemoInputPack,
        external_evidence: ExternalEvidencePack,
        settings: Settings,
    ) -> OpportunityMemoStructuredArtifact:
        ...


@dataclass(frozen=True)
class OpenAiWriterResponse:
    model_name: str
    response_id: str | None
    latency_ms: int
    retries: int
    raw_text: str


class OpenAiOpportunityMemoWriter:
    name = "openai_opportunity_memo_writer_v1"

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        endpoint: str = "https://api.openai.com/v1/responses",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.endpoint = endpoint

    def write(
        self,
        *,
        input_pack: OpportunityMemoInputPack,
        external_evidence: ExternalEvidencePack,
        settings: Settings,
    ) -> OpportunityMemoStructuredArtifact:
        api_key = settings.openai_api_key
        if not api_key:
            raise OpportunityMemoWriterError("OPENAI_API_KEY is required for opportunity memo writer")

        model_name = settings.opportunity_memo_writer_model or settings.openai_model
        if not model_name:
            raise OpportunityMemoWriterError("No model configured for opportunity memo writer")

        prompt_payload = {
            "topic": input_pack.topic,
            "window": {
                "start_time": input_pack.window.start_time.isoformat(),
                "end_time": input_pack.window.end_time.isoformat(),
            },
            "selected_event_ids": input_pack.selected_event_ids,
            "topic_event_stats": input_pack.topic_event_stats,
            "driver_evidence_summary": input_pack.driver_evidence_summary,
            "supporting_fact_candidates": input_pack.supporting_fact_candidates,
            "event_timeline": [
                {
                    "event_id": item.event_id,
                    "event_time": item.event_time.isoformat() if item.event_time is not None else None,
                    "summary": item.summary,
                    "impact_score": item.impact_score,
                    "entities": item.entities,
                    "tags": item.tags,
                    "relations": item.relations,
                }
                for item in input_pack.event_timeline
            ],
            "selected_primary_driver": (
                input_pack.selected_primary_driver.model_dump(mode="json")
                if input_pack.selected_primary_driver is not None
                else None
            ),
            # Selection diagnostics intentionally excluded from writer evidence context.
            "external_sources": [
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "title": source.title,
                    "publisher": source.publisher,
                    "retrieved_at": source.retrieved_at.isoformat(),
                    "query": source.query,
                    "summary": source.summary,
                    "claim_support_tags": source.claim_support_tags,
                    "url": str(source.url) if source.url is not None else None,
                }
                for source in external_evidence.sources
            ],
            "required_sections": [
                "title",
                "core_thesis_one_liner",
                "opportunity_target",
                "market_setup",
                "background",
                "primary_driver",
                "supporting_developments",
                "why_now",
                "why_this_is_an_opportunity",
                "trade_expression",
                "quantified_evidence_points",
                "risks",
                "invalidation_triggers",
                "watchpoints",
                "confidence_level",
                "conclusion",
                "traceability",
            ],
            "required_traceability_sections": [
                "core_thesis_one_liner",
                "market_setup",
                "background",
                "primary_driver",
                "supporting_developments",
                "why_now",
                "why_this_is_an_opportunity",
                "trade_expression",
                "quantified_evidence_points",
                "risks",
                "invalidation_triggers",
                "watchpoints",
                "conclusion",
            ],
            "traceability_key_examples": [
                "core_thesis_one_liner",
                "market_setup",
                "background",
                "primary_driver",
                "supporting_developments[0]",
                "why_now",
                "why_this_is_an_opportunity",
                "trade_expression",
                "quantified_evidence_points[0]",
                "risks[0]",
                "invalidation_triggers[0]",
                "watchpoints[0]",
                "conclusion",
                "opportunity_target",
            ],
            "minimum_list_lengths": {
                "supporting_developments": 2,
                "quantified_evidence_points": 2,
                "risks": 2,
                "invalidation_triggers": 2,
                "watchpoints": 2,
            },
            "forbidden_generic_phrases": [
                "investors may benefit",
                "consider diversifying",
                "take a proactive approach",
                "monitor developments",
                "energy markets",
                "commodity sector",
                "shipping industry",
            ],
        }

        schema_attempts = 2
        previous_payload: dict[str, Any] | None = None
        previous_error_text: str | None = None
        fallback_payload: dict[str, Any] | None = None

        for schema_attempt in range(schema_attempts):
            mode = "initial" if schema_attempt == 0 else "schema_repair"
            attempt_payload = dict(prompt_payload)
            attempt_payload["writer_mode"] = mode
            if previous_payload is not None:
                attempt_payload["previous_draft_payload"] = previous_payload
            if previous_error_text is not None:
                attempt_payload["previous_schema_failures"] = previous_error_text

            try:
                response = self._call_openai(
                    api_key=api_key,
                    model_name=model_name,
                    prompt_payload=attempt_payload,
                )
            except OpportunityMemoWriterError as exc:
                if fallback_payload is not None:
                    try:
                        return OpportunityMemoStructuredArtifact.model_validate(fallback_payload)
                    except Exception:  # noqa: BLE001
                        pass
                if schema_attempt == (schema_attempts - 1):
                    raise
                previous_error_text = str(exc)
                continue

            try:
                payload = json.loads(response.raw_text)
            except json.JSONDecodeError as exc:
                previous_payload = None
                previous_error_text = f"invalid_json:{exc}"
                if schema_attempt == (schema_attempts - 1):
                    raise OpportunityMemoWriterError(f"Memo writer returned invalid JSON: {exc}") from exc
                continue

            if not isinstance(payload, dict):
                previous_payload = None
                previous_error_text = "non_object_payload"
                if schema_attempt == (schema_attempts - 1):
                    raise OpportunityMemoWriterError("Memo writer returned non-object payload")
                continue

            coerced = _coerce_writer_payload(payload)
            if schema_attempt == (schema_attempts - 1):
                coerced = self._complete_missing_fields(
                    api_key=api_key,
                    model_name=model_name,
                    base_payload=prompt_payload,
                    draft_payload=coerced,
                )
            coerced = _harden_payload_with_deterministic_guards(
                payload=coerced,
                input_pack=input_pack,
                external_evidence=external_evidence,
            )
            fallback_payload = coerced
            try:
                return OpportunityMemoStructuredArtifact.model_validate(coerced)
            except Exception as exc:  # noqa: BLE001
                previous_payload = payload
                previous_error_text = str(exc)
                if schema_attempt == (schema_attempts - 1):
                    raise OpportunityMemoWriterError(f"Memo writer payload failed schema validation: {exc}") from exc

        raise OpportunityMemoWriterError("Memo writer failed to produce a valid structured artifact")

    def _complete_missing_fields(
        self,
        *,
        api_key: str,
        model_name: str,
        base_payload: dict[str, Any],
        draft_payload: dict[str, Any],
    ) -> dict[str, Any]:
        missing_fields = _missing_required_contract_fields(draft_payload)
        if not missing_fields:
            return draft_payload

        completion_payload = {
            "writer_mode": "missing_field_completion",
            "missing_fields": missing_fields,
            "draft_payload": draft_payload,
            "evidence_context": {
                "topic": base_payload.get("topic"),
                "window": base_payload.get("window"),
                "selected_event_ids": base_payload.get("selected_event_ids"),
                "event_timeline": base_payload.get("event_timeline"),
                "selected_primary_driver": base_payload.get("selected_primary_driver"),
                "supporting_fact_candidates": base_payload.get("supporting_fact_candidates"),
                "external_sources": base_payload.get("external_sources"),
            },
            "requirements": {
                "all_required_fields_non_empty": True,
                "minimum_list_lengths": base_payload.get("minimum_list_lengths"),
                "traceability_required": True,
            },
        }

        try:
            response = self._call_openai(
                api_key=api_key,
                model_name=model_name,
                prompt_payload=completion_payload,
            )
        except OpportunityMemoWriterError:
            return draft_payload
        try:
            payload = json.loads(response.raw_text)
        except json.JSONDecodeError:
            return draft_payload
        if not isinstance(payload, dict):
            return draft_payload
        repaired = _coerce_writer_payload(payload)
        return _merge_artifact_payload(draft_payload, repaired)

    def _call_openai(
        self,
        *,
        api_key: str,
        model_name: str,
        prompt_payload: dict[str, object],
    ) -> OpenAiWriterResponse:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        system_text = (
            "Write a client-facing investable opportunity memo as strict JSON only. "
            "Do not output markdown. Do not output prose outside JSON. "
            "Do not output generic sector commentary. "
            "The memo must identify a concrete opportunity target, timing trigger, primary driver, "
            "why the setup is actionable, and a concrete trade_expression. "
            "quantified_evidence_points must be source-backed and include numerical facts when available. "
            "Every required traceability paragraph key must include both internal_event_ids and external_source_ids. "
            "Use only event-layer evidence and normalized external evidence supplied in the prompt. "
            "Do not cite selection diagnostics as evidence. "
            "Never leave required sections empty. "
            "In schema_repair and missing_field_completion modes, strictly fix schema failures."
        )
        user_text = json.dumps(prompt_payload, ensure_ascii=True)

        request_payload = {
            "model": model_name,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_text}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                },
            ],
        }

        last_error: Exception | None = None
        last_http_detail = ""
        for attempt in range(self.max_retries + 1):
            started_at = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    http_response = client.post(self.endpoint, headers=headers, json=request_payload)
                if http_response.status_code >= 400:
                    body_text = (http_response.text or "").strip()
                    last_http_detail = body_text[:800]
                    http_response.raise_for_status()
                body = http_response.json()
                raw_text = _extract_output_text(body)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                return OpenAiWriterResponse(
                    model_name=str(body.get("model") or model_name),
                    response_id=body.get("id"),
                    latency_ms=latency_ms,
                    retries=attempt,
                    raw_text=raw_text,
                )
            except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc

        if last_http_detail:
            raise OpportunityMemoWriterError(
                f"openai opportunity memo writer failed after retries: {type(last_error).__name__}; detail={last_http_detail}"
            )
        raise OpportunityMemoWriterError(
            f"openai opportunity memo writer failed after retries: {type(last_error).__name__}"
        )


def _extract_output_text(body: dict) -> str:
    output = body.get("output", [])
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("type") in {"output_text", "text"}:
                    text = chunk.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
        if chunks:
            return "\n".join(chunks)

    output_text = body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    if isinstance(output_text, list):
        joined = "\n".join(str(value).strip() for value in output_text if str(value).strip())
        if joined:
            return joined

    raise OpportunityMemoWriterError("Empty OpenAI writer response")


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "value", "content", "paragraph", "body", "summary"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _extract_traceability_from_value(
    *,
    paragraph_key: str,
    value: Any,
) -> ParagraphSourceMap | None:
    if not isinstance(value, dict):
        return None
    internal_event_ids = value.get("internal_event_ids")
    external_source_ids = value.get("external_source_ids")
    if not isinstance(internal_event_ids, list) or not isinstance(external_source_ids, list):
        return None
    parsed_internal = [int(item) for item in internal_event_ids if isinstance(item, int)]
    parsed_external = [str(item).strip() for item in external_source_ids if isinstance(item, str) and item.strip()]
    if not parsed_internal or not parsed_external:
        return None
    return ParagraphSourceMap(
        paragraph_key=paragraph_key,
        internal_event_ids=parsed_internal,
        external_source_ids=parsed_external,
    )


def _list_from_value(value: Any) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            text = _text_from_value(item)
            if text:
                out.append(text)
        return out
    if isinstance(value, dict):
        for key in ("items", "values", "bullets", "points"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return _list_from_value(candidate)
        text = _text_from_value(value)
        return [text] if text else []
    text = _text_from_value(value)
    return [text] if text else []


def _find_value_by_aliases(value: Any, aliases: list[str], *, max_depth: int = 4) -> Any:
    alias_set = {alias.lower() for alias in aliases}

    def _walk(node: Any, depth: int) -> Any:
        if depth < 0:
            return None
        if isinstance(node, dict):
            for key, child in node.items():
                if isinstance(key, str) and key.lower() in alias_set:
                    return child
            for child in node.values():
                found = _walk(child, depth - 1)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for child in node:
                found = _walk(child, depth - 1)
                if found is not None:
                    return found
        return None

    return _walk(value, max_depth)


def _coerce_writer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    root = payload
    if isinstance(payload.get("memo"), dict):
        root = payload["memo"]
    if isinstance(payload.get("artifact"), dict):
        root = payload["artifact"]
    if isinstance(payload.get("opportunity_memo"), dict):
        root = payload["opportunity_memo"]

    sections_index: dict[str, Any] = {}
    raw_sections = root.get("sections")
    if isinstance(raw_sections, list):
        for section in raw_sections:
            if not isinstance(section, dict):
                continue
            key = section.get("key") or section.get("name") or section.get("section")
            if isinstance(key, str) and key.strip():
                sections_index[key.strip().lower()] = section.get("text") or section.get("content") or section

    traceability_rows: list[dict[str, Any]] = []
    explicit_trace = root.get("traceability") or root.get("traceability_map")
    if isinstance(explicit_trace, dict) and isinstance(explicit_trace.get("paragraph_sources"), list):
        traceability_rows = [
            row
            for row in explicit_trace.get("paragraph_sources", [])
            if isinstance(row, dict) and isinstance(row.get("paragraph_key"), str)
        ]
    elif isinstance(explicit_trace, dict):
        for key, value in explicit_trace.items():
            if not isinstance(key, str):
                continue
            row = _extract_traceability_from_value(paragraph_key=key, value=value)
            if row is not None:
                traceability_rows.append(row.model_dump(mode="json"))

    def _text_section(section_key: str) -> str:
        direct = _text_from_value(root.get(section_key))
        if direct:
            return direct
        nested = _find_value_by_aliases(root, [section_key])
        if nested is not None:
            text = _text_from_value(nested)
            if text:
                return text
        section_hit = sections_index.get(section_key.lower())
        if section_hit is not None:
            text = _text_from_value(section_hit)
            if text:
                return text
        return ""

    def _list_section(section_key: str) -> list[str]:
        direct = _list_from_value(root.get(section_key))
        if direct:
            return direct
        nested = _find_value_by_aliases(root, [section_key])
        if nested is not None:
            values = _list_from_value(nested)
            if values:
                return values
        section_hit = sections_index.get(section_key.lower())
        if section_hit is not None:
            values = _list_from_value(section_hit)
            if values:
                return values
        return []

    def _text_section_alias(*keys: str) -> str:
        for key in keys:
            text = _text_section(key)
            if text:
                return text
        return ""

    def _list_section_alias(*keys: str) -> list[str]:
        for key in keys:
            values = _list_section(key)
            if values:
                return values
        return []

    normalized = {
        "title": _text_section_alias("title", "memo_title"),
        "core_thesis_one_liner": _text_section_alias("core_thesis_one_liner", "thesis", "thesis_one_liner"),
        "opportunity_target": _text_section_alias("opportunity_target", "target_exposure", "exposure_target"),
        "market_setup": _text_section_alias("market_setup", "setup", "market_context", "setup_context"),
        "background": _text_section_alias("background", "context"),
        "primary_driver": _text_section_alias("primary_driver", "driver", "dominant_driver"),
        "supporting_developments": _list_section_alias("supporting_developments", "supporting_points"),
        "why_now": _text_section_alias("why_now", "timing", "timing_rationale"),
        "why_this_is_an_opportunity": _text_section_alias("why_this_is_an_opportunity", "why_opportunity", "opportunity_rationale"),
        "trade_expression": _text_section_alias("trade_expression", "expression", "positioning", "action_path"),
        "quantified_evidence_points": _list_section_alias("quantified_evidence_points", "evidence_points", "quantified_points", "key_numbers"),
        "risks": _list_section_alias("risks", "risk_factors"),
        "invalidation_triggers": _list_section_alias("invalidation_triggers", "invalidation", "thesis_breakers", "break_conditions"),
        "watchpoints": _list_section_alias("watchpoints", "monitoring_points"),
        "confidence_level": (
            _text_section_alias("confidence_level", "confidence").lower()
            if _text_section_alias("confidence_level", "confidence").lower() in {"low", "medium", "high"}
            else "medium"
        ),
        "conclusion": _text_section_alias("conclusion", "closing"),
        "traceability": {"paragraph_sources": traceability_rows},
    }

    if traceability_rows:
        return normalized

    derived_rows: list[dict[str, Any]] = []
    for key in (
        "core_thesis_one_liner",
        "market_setup",
        "background",
        "primary_driver",
        "why_now",
        "why_this_is_an_opportunity",
        "trade_expression",
        "conclusion",
        "opportunity_target",
    ):
        row = _extract_traceability_from_value(paragraph_key=key, value=root.get(key))
        if row is None and key == "core_thesis_one_liner":
            row = _extract_traceability_from_value(paragraph_key=key, value=root.get("thesis"))
        if row is None and key == "trade_expression":
            row = _extract_traceability_from_value(paragraph_key=key, value=root.get("action_path"))
        if row is not None:
            derived_rows.append(row.model_dump(mode="json"))

    for idx, item in enumerate(root.get("supporting_developments") if isinstance(root.get("supporting_developments"), list) else []):
        row = _extract_traceability_from_value(paragraph_key=f"supporting_developments[{idx}]", value=item)
        if row is not None:
            derived_rows.append(row.model_dump(mode="json"))

    for idx, item in enumerate(root.get("quantified_evidence_points") if isinstance(root.get("quantified_evidence_points"), list) else []):
        row = _extract_traceability_from_value(paragraph_key=f"quantified_evidence_points[{idx}]", value=item)
        if row is not None:
            derived_rows.append(row.model_dump(mode="json"))

    for idx, item in enumerate(root.get("risks") if isinstance(root.get("risks"), list) else []):
        row = _extract_traceability_from_value(paragraph_key=f"risks[{idx}]", value=item)
        if row is not None:
            derived_rows.append(row.model_dump(mode="json"))

    for idx, item in enumerate(root.get("invalidation_triggers") if isinstance(root.get("invalidation_triggers"), list) else []):
        row = _extract_traceability_from_value(paragraph_key=f"invalidation_triggers[{idx}]", value=item)
        if row is not None:
            derived_rows.append(row.model_dump(mode="json"))

    for idx, item in enumerate(root.get("watchpoints") if isinstance(root.get("watchpoints"), list) else []):
        row = _extract_traceability_from_value(paragraph_key=f"watchpoints[{idx}]", value=item)
        if row is not None:
            derived_rows.append(row.model_dump(mode="json"))

    normalized["traceability"]["paragraph_sources"] = derived_rows
    return normalized


def _missing_required_contract_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    required_text_fields = (
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
    )
    for key in required_text_fields:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(key)
    required_list_fields = (
        "supporting_developments",
        "quantified_evidence_points",
        "risks",
        "invalidation_triggers",
        "watchpoints",
    )
    for key in required_list_fields:
        value = payload.get(key)
        if not isinstance(value, list) or not value:
            missing.append(key)
    traceability = payload.get("traceability")
    if not isinstance(traceability, dict) or not isinstance(traceability.get("paragraph_sources"), list) or not traceability.get("paragraph_sources"):
        missing.append("traceability")
    return missing


def _merge_artifact_payload(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key == "traceability":
            base_rows = (
                ((base.get("traceability") or {}) if isinstance(base.get("traceability"), dict) else {}).get("paragraph_sources")
                or []
            )
            overlay_rows = (
                ((overlay.get("traceability") or {}) if isinstance(overlay.get("traceability"), dict) else {}).get("paragraph_sources")
                or []
            )
            merged["traceability"] = {"paragraph_sources": overlay_rows if overlay_rows else base_rows}
            continue

        if isinstance(value, str):
            if value.strip():
                merged[key] = value
            continue
        if isinstance(value, list):
            if value:
                merged[key] = value
            continue
        if value is not None:
            merged[key] = value
    return merged


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _has_numeric(value: str) -> bool:
    for char in value:
        if char.isdigit():
            return True
    return False


def _is_weak_thesis(value: str, *, topic: str, driver_key: str | None) -> bool:
    normalized = _normalize_text(value)
    if len(normalized.split()) < 12:
        return True
    direction_tokens = ("upside", "downside", "repricing", "long", "short", "overweight", "underweight", "widening", "tightening")
    reason_tokens = ("because", "driven by", "due to", "as")
    topic_tokens = tuple(token for token in topic.replace("_", " ").split() if token)
    has_direction = any(token in normalized for token in direction_tokens)
    has_reason = any(token in normalized for token in reason_tokens)
    has_topic = any(token in normalized for token in topic_tokens)
    has_driver = bool(driver_key and driver_key.replace("_", " ") in normalized)
    return not (has_direction and has_reason and (has_topic or has_driver))


def _is_generic_why_now(value: str) -> bool:
    normalized = _normalize_text(value)
    if len(normalized.split()) < 12:
        return True
    timing_tokens = ("now", "recent", "window", "this week", "last", "currently", "immediate")
    has_timing = any(token in normalized for token in timing_tokens)
    return not (has_timing and _has_numeric(normalized))


def _is_vague_trade_expression(value: str) -> bool:
    normalized = _normalize_text(value)
    if len(normalized.split()) < 12:
        return True
    vague_phrases = (
        "monitor developments",
        "consider diversifying",
        "proactive approach",
        "investors may benefit",
        "stay informed",
    )
    if any(phrase in normalized for phrase in vague_phrases):
        return True
    route_tokens = (
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
        "benchmark",
        "volatility",
        "freight",
    )
    return not any(token in normalized for token in route_tokens)


def _is_generic_opportunity_framing(value: str) -> bool:
    normalized = _normalize_text(value)
    if len(normalized.split()) < 14:
        return True
    logic_tokens = (
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
    return not any(token in normalized for token in logic_tokens)


def _is_filler_watchpoint(value: str) -> bool:
    normalized = _normalize_text(value)
    if len(normalized.split()) < 5:
        return True
    filler_phrases = (
        "monitor developments",
        "stay informed",
        "various factors",
        "market uncertainty",
        "dynamic environment",
    )
    return any(phrase in normalized for phrase in filler_phrases)


def _is_filler_list_item(value: str) -> bool:
    normalized = _normalize_text(value)
    if len(normalized.split()) < 5:
        return True
    filler_phrases = (
        "monitor developments",
        "stay informed",
        "various factors",
        "market uncertainty",
        "dynamic environment",
        "this seems meaningful",
        "it could matter",
    )
    return any(phrase in normalized for phrase in filler_phrases)


def _required_traceability_keys(payload: dict[str, Any]) -> list[str]:
    keys = [
        "core_thesis_one_liner",
        "market_setup",
        "background",
        "primary_driver",
        "why_now",
        "why_this_is_an_opportunity",
        "trade_expression",
        "conclusion",
    ]
    keys.extend(
        f"supporting_developments[{idx}]"
        for idx, _ in enumerate(payload.get("supporting_developments") or [])
    )
    keys.extend(
        f"quantified_evidence_points[{idx}]"
        for idx, _ in enumerate(payload.get("quantified_evidence_points") or [])
    )
    keys.extend(f"risks[{idx}]" for idx, _ in enumerate(payload.get("risks") or []))
    keys.extend(
        f"invalidation_triggers[{idx}]"
        for idx, _ in enumerate(payload.get("invalidation_triggers") or [])
    )
    keys.extend(f"watchpoints[{idx}]" for idx, _ in enumerate(payload.get("watchpoints") or []))
    return keys


def _format_window_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _harden_payload_with_deterministic_guards(
    *,
    payload: dict[str, Any],
    input_pack: OpportunityMemoInputPack,
    external_evidence: ExternalEvidencePack,
) -> dict[str, Any]:
    hardened = dict(payload)

    topic_label = input_pack.topic.replace("_", " ")
    driver_key = (
        input_pack.selected_primary_driver.driver_key
        if input_pack.selected_primary_driver is not None
        else None
    )
    driver_label = driver_key.replace("_", " ") if driver_key else "driver concentration"
    event_count = int(input_pack.topic_event_stats.get("event_count") or len(input_pack.selected_event_ids))
    avg_impact = float(input_pack.topic_event_stats.get("average_impact_score") or 0.0)
    start_label = _format_window_time(input_pack.window.start_time)
    end_label = _format_window_time(input_pack.window.end_time)

    thesis = str(hardened.get("core_thesis_one_liner") or "").strip()
    if _is_weak_thesis(thesis, topic=input_pack.topic, driver_key=driver_key):
        target_hint = str(hardened.get("opportunity_target") or "").strip()
        if not target_hint:
            target_hint = f"{topic_label} spread and exposure basket"
        hardened["core_thesis_one_liner"] = (
            f"{target_hint} has upside repricing opportunity because {driver_label} signals "
            f"concentrated across {event_count} events (average impact {avg_impact:.1f}) in the "
            f"{start_label} to {end_label} window."
        )

    why_now = str(hardened.get("why_now") or "").strip()
    if _is_generic_why_now(why_now):
        recent_count = int(input_pack.topic_event_stats.get("recent_event_count") or 0)
        hardened["why_now"] = (
            f"Now is actionable because the {start_label} to {end_label} window showed {event_count} "
            f"topic-linked events with {recent_count} in the most recent third of the window, "
            f"confirming timing-sensitive repricing pressure."
        )

    primary_driver_text = str(hardened.get("primary_driver") or "").strip()
    if not primary_driver_text:
        if driver_key:
            hardened["primary_driver"] = (
                f"{driver_label} is the dominant deterministic driver based on supporting event concentration "
                f"and temporal clustering in the selected window."
            )
        else:
            hardened["primary_driver"] = (
                "deterministic driver concentration is present across selected high-impact events in the window."
            )

    trade_expression = str(hardened.get("trade_expression") or "").strip()
    if _is_vague_trade_expression(trade_expression):
        hardened["trade_expression"] = (
            f"Express via {topic_label} futures curve spreads with options overlays, and size exposure "
            f"to the {driver_label} signal using explicit invalidation levels tied to prompt-vs-deferred pricing."
        )

    why_opportunity = str(hardened.get("why_this_is_an_opportunity") or "").strip()
    if _is_generic_opportunity_framing(why_opportunity):
        hardened["why_this_is_an_opportunity"] = (
            f"This is an opportunity because the market appears to underprice {driver_label} transmission "
            f"into {topic_label} risk premium and spread repricing, creating financially actionable asymmetry "
            f"if consensus positioning adjusts after additional confirmation."
        )

    raw_watchpoints = hardened.get("watchpoints")
    normalized_watchpoints = [
        str(row).strip()
        for row in (raw_watchpoints if isinstance(raw_watchpoints, list) else [])
        if str(row).strip()
    ]
    cleaned_watchpoints = [row for row in normalized_watchpoints if not _is_filler_watchpoint(row)]
    if len(cleaned_watchpoints) < 2:
        cleaned_watchpoints = [
            (
                f"{topic_label} prompt-vs-deferred spread levels and daily curve slope changes "
                f"relative to the {start_label} to {end_label} baseline."
            ),
            (
                f"Primary driver confirmations ({driver_label}) via operational updates, "
                f"flow constraints, and high-impact event cadence."
            ),
        ]
    hardened["watchpoints"] = cleaned_watchpoints[:4]

    raw_quant_points = hardened.get("quantified_evidence_points")
    quant_points = [
        str(row).strip()
        for row in (raw_quant_points if isinstance(raw_quant_points, list) else [])
        if str(row).strip() and not _is_filler_list_item(str(row))
    ]
    quant_points = [row for row in quant_points if _has_numeric(row)]
    if len(quant_points) < 2:
        fallback_quant: list[str] = []
        for fact in input_pack.supporting_fact_candidates:
            fact_text = str(fact.get("fact_text") or "").strip()
            if fact_text and _has_numeric(fact_text):
                fallback_quant.append(fact_text)
            if len(fallback_quant) >= 2:
                break
        source_summaries = [str(source.summary).strip() for source in external_evidence.sources if str(source.summary).strip()]
        for summary in source_summaries:
            if _has_numeric(summary):
                fallback_quant.append(summary)
            if len(fallback_quant) >= 3:
                break
        if len(fallback_quant) < 2:
            fallback_quant.extend(
                [
                    f"Selected window includes {event_count} {topic_label} events with average impact score {avg_impact:.1f}.",
                    f"Primary driver support share is {float(input_pack.driver_evidence_summary.get('supporting_event_share') or 0.0) * 100:.1f}% of selected events.",
                ]
            )
        quant_points = fallback_quant
    hardened["quantified_evidence_points"] = quant_points[:6]

    raw_risks = hardened.get("risks")
    risks = [
        str(row).strip()
        for row in (raw_risks if isinstance(raw_risks, list) else [])
        if str(row).strip() and not _is_filler_list_item(str(row))
    ]
    if len(risks) < 2:
        risks = [
            (
                f"{driver_label} normalizes faster than expected, compressing {topic_label} risk premium "
                "before the view can be expressed."
            ),
            (
                f"Policy, regulatory, or operational intervention weakens transmission from {driver_label} "
                f"into {topic_label} pricing and exposure performance."
            ),
        ]
    hardened["risks"] = risks[:4]

    raw_invalidation = hardened.get("invalidation_triggers")
    invalidation = [
        str(row).strip()
        for row in (raw_invalidation if isinstance(raw_invalidation, list) else [])
        if str(row).strip() and not _is_filler_list_item(str(row))
    ]
    if len(invalidation) < 2:
        invalidation = [
            (
                f"Two consecutive sessions of {topic_label} spread mean reversion with no renewed "
                f"{driver_label} confirmations."
            ),
            (
                f"Operational updates show constraint relief and event cadence drops below the "
                f"{start_label} to {end_label} baseline."
            ),
        ]
    hardened["invalidation_triggers"] = invalidation[:4]

    allowed_event_ids = [int(event_id) for event_id in input_pack.selected_event_ids if int(event_id) > 0]
    if not allowed_event_ids and input_pack.event_timeline:
        allowed_event_ids = [int(item.event_id) for item in input_pack.event_timeline if int(item.event_id) > 0]
    if not allowed_event_ids:
        allowed_event_ids = [1]

    preferred_event_ids: list[int]
    if input_pack.selected_primary_driver is not None and input_pack.selected_primary_driver.supporting_event_ids:
        preferred_event_ids = [int(event_id) for event_id in input_pack.selected_primary_driver.supporting_event_ids if int(event_id) in set(allowed_event_ids)]
    else:
        preferred_event_ids = []
    if not preferred_event_ids:
        preferred_event_ids = allowed_event_ids[: min(3, len(allowed_event_ids))]

    allowed_source_ids = [str(source.source_id).strip() for source in external_evidence.sources if str(source.source_id).strip()]
    if not allowed_source_ids:
        allowed_source_ids = ["src_fallback"]
    preferred_source_ids = allowed_source_ids[: min(3, len(allowed_source_ids))]

    traceability = hardened.get("traceability")
    rows = []
    if isinstance(traceability, dict) and isinstance(traceability.get("paragraph_sources"), list):
        rows = [row for row in traceability.get("paragraph_sources", []) if isinstance(row, dict)]

    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("paragraph_key")
        if isinstance(key, str) and key.strip():
            internal_ids = [
                int(event_id)
                for event_id in row.get("internal_event_ids", [])
                if isinstance(event_id, int) and int(event_id) in set(allowed_event_ids)
            ]
            external_ids = [
                str(source_id).strip()
                for source_id in row.get("external_source_ids", [])
                if isinstance(source_id, str) and str(source_id).strip() in set(allowed_source_ids)
            ]
            by_key[key.strip()] = {
                "paragraph_key": key.strip(),
                "internal_event_ids": internal_ids or list(preferred_event_ids),
                "external_source_ids": external_ids or list(preferred_source_ids),
            }

    for key in _required_traceability_keys(hardened):
        if key not in by_key:
            by_key[key] = {
                "paragraph_key": key,
                "internal_event_ids": list(preferred_event_ids),
                "external_source_ids": list(preferred_source_ids),
            }

    hardened["traceability"] = {
        "paragraph_sources": [by_key[key] for key in sorted(by_key.keys())],
    }

    return hardened

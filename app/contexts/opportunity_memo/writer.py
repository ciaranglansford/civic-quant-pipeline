from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from ...config import Settings
from .contracts import ExternalEvidencePack, OpportunityMemoInputPack, OpportunityMemoStructuredArtifact


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
                "thesis",
                "opportunity_target",
                "background",
                "primary_driver",
                "supporting_developments",
                "why_now",
                "action_path",
                "risks",
                "watchpoints",
                "conclusion",
                "traceability",
            ],
            "required_traceability_sections": [
                "thesis",
                "background",
                "primary_driver",
                "supporting_developments",
                "why_now",
                "action_path",
                "risks",
                "watchpoints",
                "conclusion",
            ],
            "traceability_key_examples": [
                "thesis",
                "background",
                "primary_driver",
                "supporting_developments[0]",
                "why_now",
                "action_path",
                "risks[0]",
                "watchpoints[0]",
                "conclusion",
                "opportunity_target",
            ],
        }

        response = self._call_openai(
            api_key=api_key,
            model_name=model_name,
            prompt_payload=prompt_payload,
        )

        try:
            payload = json.loads(response.raw_text)
        except json.JSONDecodeError as exc:
            raise OpportunityMemoWriterError(f"Memo writer returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise OpportunityMemoWriterError("Memo writer returned non-object payload")

        try:
            return OpportunityMemoStructuredArtifact.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise OpportunityMemoWriterError(f"Memo writer payload failed schema validation: {exc}") from exc

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
            "Write a client-facing investment opportunity memo as strict JSON only. "
            "Do not include markdown. Preserve uncertainty and attribution where evidence is uncertain. "
            "Every thesis-bearing paragraph key must include both internal_event_ids and external_source_ids. "
            "Do not cite selection diagnostics as evidence."
        )
        user_text = json.dumps(prompt_payload, ensure_ascii=True)

        request_payload = {
            "model": model_name,
            "text": {"format": {"type": "json_object"}},
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
        for attempt in range(self.max_retries + 1):
            started_at = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    http_response = client.post(self.endpoint, headers=headers, json=request_payload)
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

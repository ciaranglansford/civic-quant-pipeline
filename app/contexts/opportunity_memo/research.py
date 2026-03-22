from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from ...config import Settings
from .contracts import (
    ExternalEvidencePack,
    ExternalEvidenceSource,
    OpportunityMemoInputPack,
    OpportunityResearchPlan,
    ResearchNeed,
)


class OpportunityResearchError(RuntimeError):
    pass


class OpportunityResearchProvider(Protocol):
    name: str

    def retrieve(
        self,
        *,
        input_pack: OpportunityMemoInputPack,
        plan: OpportunityResearchPlan,
        settings: Settings,
    ) -> ExternalEvidencePack:
        ...


@dataclass(frozen=True)
class OpenAiResearchResponse:
    model_name: str
    response_id: str | None
    latency_ms: int
    retries: int
    raw_text: str


class OpenAiOpportunityResearchProvider:
    name = "openai_web_research_v1"

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

    def retrieve(
        self,
        *,
        input_pack: OpportunityMemoInputPack,
        plan: OpportunityResearchPlan,
        settings: Settings,
    ) -> ExternalEvidencePack:
        api_key = settings.openai_api_key
        if not api_key:
            raise OpportunityResearchError("OPENAI_API_KEY is required for opportunity memo research retrieval")

        model_name = settings.opportunity_memo_research_model or settings.openai_model
        if not model_name:
            raise OpportunityResearchError("No model configured for opportunity memo research retrieval")

        prompt_payload = {
            "topic": input_pack.topic,
            "window": {
                "start_time": input_pack.window.start_time.isoformat(),
                "end_time": input_pack.window.end_time.isoformat(),
            },
            "primary_driver": (
                input_pack.selected_primary_driver.driver_key
                if input_pack.selected_primary_driver is not None
                else None
            ),
            "queries": plan.queries,
            "needs": [need.model_dump(mode="json") for need in plan.needs],
            "selected_event_ids": input_pack.selected_event_ids,
            "event_summaries": [
                {
                    "event_id": row.event_id,
                    "summary": row.summary,
                    "impact_score": row.impact_score,
                }
                for row in input_pack.event_timeline[:10]
            ],
        }

        response = self._call_openai(
            api_key=api_key,
            model_name=model_name,
            prompt_payload=prompt_payload,
        )

        retrieved_at = datetime.utcnow()
        normalized_sources = _normalize_sources(
            raw_text=response.raw_text,
            retrieved_at=retrieved_at,
            fallback_queries=plan.queries,
        )

        return ExternalEvidencePack(
            topic=input_pack.topic,
            provider_name=self.name,
            sources=normalized_sources,
            retrieval_diagnostics={
                "model_name": response.model_name,
                "response_id": response.response_id,
                "latency_ms": response.latency_ms,
                "retries": response.retries,
                "query_count": len(plan.queries),
                "source_count": len(normalized_sources),
            },
        )

    def _call_openai(
        self,
        *,
        api_key: str,
        model_name: str,
        prompt_payload: dict[str, object],
    ) -> OpenAiResearchResponse:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        system_text = (
            "Return strict JSON only with shape: "
            "{\"sources\":[{\"source_id\":str,\"source_type\":str,\"title\":str,\"publisher\":str|null,"
            "\"query\":str,\"summary\":str,\"claim_support_tags\":[str],\"url\":str|null}]}. "
            "Do not include markdown or additional keys."
        )
        user_text = json.dumps(prompt_payload, ensure_ascii=True)

        request_payload = {
            "model": model_name,
            "text": {"format": {"type": "json_object"}},
            "tools": [{"type": "web_search_preview"}],
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
                return OpenAiResearchResponse(
                    model_name=str(body.get("model") or model_name),
                    response_id=body.get("id"),
                    latency_ms=latency_ms,
                    retries=attempt,
                    raw_text=raw_text,
                )
            except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc

        raise OpportunityResearchError(
            f"openai research retrieval failed after retries: {type(last_error).__name__}"
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

    raise OpportunityResearchError("Empty OpenAI research response")


def _normalize_sources(
    *,
    raw_text: str,
    retrieved_at: datetime,
    fallback_queries: list[str],
) -> list[ExternalEvidenceSource]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise OpportunityResearchError(f"Research provider did not return valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise OpportunityResearchError("Research provider payload must be a JSON object")

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise OpportunityResearchError("Research provider payload missing 'sources' list")

    normalized: list[ExternalEvidenceSource] = []
    for idx, row in enumerate(raw_sources):
        if not isinstance(row, dict):
            continue

        source_id = str(row.get("source_id") or f"src_{idx + 1:02d}").strip() or f"src_{idx + 1:02d}"
        source_type = str(row.get("source_type") or "web").strip() or "web"
        title = str(row.get("title") or "Untitled source").strip() or "Untitled source"
        publisher_raw = row.get("publisher")
        publisher = str(publisher_raw).strip() if isinstance(publisher_raw, str) and publisher_raw.strip() else None

        query_raw = row.get("query")
        query = str(query_raw).strip() if isinstance(query_raw, str) and query_raw.strip() else ""
        if not query:
            query = fallback_queries[min(idx, max(0, len(fallback_queries) - 1))] if fallback_queries else "unspecified"

        summary = str(row.get("summary") or "").strip()
        if not summary:
            continue

        claim_support_tags: list[str] = []
        raw_tags = row.get("claim_support_tags")
        if isinstance(raw_tags, list):
            for tag in raw_tags:
                if isinstance(tag, str) and tag.strip():
                    claim_support_tags.append(tag.strip())

        url_raw = row.get("url")
        url = str(url_raw).strip() if isinstance(url_raw, str) and url_raw.strip() else None

        normalized.append(
            ExternalEvidenceSource(
                source_id=source_id,
                source_type=source_type,
                title=title,
                publisher=publisher,
                retrieved_at=retrieved_at,
                query=query,
                summary=summary,
                claim_support_tags=claim_support_tags,
                url=url,
            )
        )

    return normalized


def build_research_plan(input_pack: OpportunityMemoInputPack) -> OpportunityResearchPlan:
    driver_key = (
        input_pack.selected_primary_driver.driver_key
        if input_pack.selected_primary_driver is not None
        else "unknown_driver"
    )

    top_entity = input_pack.supporting_entities[0]["value"] if input_pack.supporting_entities else input_pack.topic
    queries = [
        f"{input_pack.topic} {driver_key} market impact latest",
        f"{input_pack.topic} {top_entity} pricing and supply context",
        f"{input_pack.topic} investment risks and positioning watchpoints",
    ]

    needs = [
        ResearchNeed(need_type="confirmation", detail="Confirm core claims linked to the primary driver."),
        ResearchNeed(need_type="context", detail="Add market context around pricing, supply-demand, and positioning."),
        ResearchNeed(need_type="examples", detail="Collect concrete examples or data points to support action path and risks."),
    ]

    return OpportunityResearchPlan(
        topic=input_pack.topic,
        primary_driver_key=driver_key,
        queries=queries,
        needs=needs,
    )

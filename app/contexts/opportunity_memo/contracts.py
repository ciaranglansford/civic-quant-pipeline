from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class TopicMappingDiagnostics(BaseModel):
    source_layer: str
    matched_fields: list[str] = Field(default_factory=list)
    reason_trail: list[str] = Field(default_factory=list)
    final_topic: str | None = None


class TopicMappingResult(BaseModel):
    event_id: int
    topic: str | None = None
    diagnostics: TopicMappingDiagnostics


class TopicRankingBreakdown(BaseModel):
    normalized_event_count: float
    normalized_weighted_impact: float
    normalized_novelty: float
    normalized_coherence: float
    normalized_actionability: float


class RankedTopicOpportunity(BaseModel):
    topic: str
    topic_score: float
    event_count: int
    weighted_impact: float
    novelty: float
    coherence: float
    actionability: float
    candidate_event_ids: list[int] = Field(default_factory=list)
    breakdown: TopicRankingBreakdown


class DriverScoreComponents(BaseModel):
    supporting_event_weight: float
    temporal_density: float
    entity_consistency: float
    external_confirmability: float


class DriverCandidate(BaseModel):
    driver_key: str
    score: float
    supporting_event_ids: list[int] = Field(default_factory=list)
    score_components: DriverScoreComponents


class MemoWindow(BaseModel):
    start_time: datetime
    end_time: datetime


class MemoEventTimelineItem(BaseModel):
    event_id: int
    event_time: datetime | None = None
    summary: str
    impact_score: float
    entities: dict[str, Any] = Field(default_factory=dict)
    tags: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class MemoSelectionDiagnostics(BaseModel):
    topic_score: float
    selection_reason: str
    topic_breakdown: dict[str, float] = Field(default_factory=dict)


class OpportunityMemoInputPack(BaseModel):
    topic: str
    window: MemoWindow
    selected_event_ids: list[int] = Field(default_factory=list)
    event_timeline: list[MemoEventTimelineItem] = Field(default_factory=list)
    candidate_driver_groups: list[DriverCandidate] = Field(default_factory=list)
    selected_primary_driver: DriverCandidate | None = None
    supporting_entities: list[dict[str, str]] = Field(default_factory=list)
    topic_event_stats: dict[str, float | int] = Field(default_factory=dict)
    driver_evidence_summary: dict[str, Any] = Field(default_factory=dict)
    supporting_fact_candidates: list[dict[str, Any]] = Field(default_factory=list)
    selection_diagnostics: MemoSelectionDiagnostics


class ResearchNeed(BaseModel):
    need_type: str
    detail: str


class OpportunityResearchPlan(BaseModel):
    topic: str
    primary_driver_key: str
    queries: list[str] = Field(default_factory=list)
    needs: list[ResearchNeed] = Field(default_factory=list)


class ExternalEvidenceSource(BaseModel):
    source_id: str
    source_type: str
    title: str
    publisher: str | None = None
    retrieved_at: datetime
    query: str
    summary: str
    claim_support_tags: list[str] = Field(default_factory=list)
    url: HttpUrl | str | None = None


class ExternalEvidencePack(BaseModel):
    topic: str
    sources: list[ExternalEvidenceSource] = Field(default_factory=list)
    provider_name: str
    retrieval_diagnostics: dict[str, Any] = Field(default_factory=dict)


class ParagraphSourceMap(BaseModel):
    paragraph_key: str
    internal_event_ids: list[int] = Field(default_factory=list)
    external_source_ids: list[str] = Field(default_factory=list)


class MemoTraceability(BaseModel):
    paragraph_sources: list[ParagraphSourceMap] = Field(default_factory=list)


class OpportunityMemoStructuredArtifact(BaseModel):
    title: str = Field(min_length=1)
    core_thesis_one_liner: str = Field(min_length=1)
    opportunity_target: str = Field(min_length=1)
    market_setup: str = Field(min_length=1)
    background: str = Field(min_length=1)
    primary_driver: str = Field(min_length=1)
    supporting_developments: list[str] = Field(default_factory=list)
    why_now: str = Field(min_length=1)
    why_this_is_an_opportunity: str = Field(min_length=1)
    trade_expression: str = Field(min_length=1)
    quantified_evidence_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    invalidation_triggers: list[str] = Field(default_factory=list)
    watchpoints: list[str] = Field(default_factory=list)
    confidence_level: Literal["low", "medium", "high"]
    conclusion: str = Field(min_length=1)
    traceability: MemoTraceability

    def paragraph_keys(self) -> list[str]:
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
        keys.extend(f"supporting_developments[{idx}]" for idx, _ in enumerate(self.supporting_developments))
        keys.extend(f"quantified_evidence_points[{idx}]" for idx, _ in enumerate(self.quantified_evidence_points))
        keys.extend(f"risks[{idx}]" for idx, _ in enumerate(self.risks))
        keys.extend(f"invalidation_triggers[{idx}]" for idx, _ in enumerate(self.invalidation_triggers))
        keys.extend(f"watchpoints[{idx}]" for idx, _ in enumerate(self.watchpoints))
        return keys


class MemoValidationIssue(BaseModel):
    code: str
    message: str


class MemoValidationResult(BaseModel):
    ok: bool
    errors: list[MemoValidationIssue] = Field(default_factory=list)
    warnings: list[MemoValidationIssue] = Field(default_factory=list)


class OpportunityMemoRunResult(BaseModel):
    run_id: int
    status: str
    selected_topic: str | None = None
    topic_score: float | None = None
    artifact_id: int | None = None
    delivery_status: str | None = None
    validation_errors: list[dict[str, str]] = Field(default_factory=list)
    message: str | None = None

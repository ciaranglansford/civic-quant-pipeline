from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


Topic = Literal[
    "macro_econ",
    "central_banks",
    "equities",
    "credit",
    "rates",
    "fx",
    "commodities",
    "crypto",
    "war_security",
    "geopolitics",
    "company_specific",
    "other",
]

Sentiment = Literal["positive", "negative", "neutral", "mixed", "unknown"]

BreakingWindow = Literal["15m", "1h", "4h", "none"]

PublishPriority = Literal["none", "low", "medium", "high"]

EventAction = Literal["create", "update", "ignore"]


class TelegramIngestPayload(BaseModel):
    source_channel_id: str
    source_channel_name: str | None = None
    telegram_message_id: str
    message_timestamp_utc: datetime
    raw_text: str
    raw_entities_if_available: Any | None = None
    forwarded_from_if_available: str | None = None


class SourceIngestPayload(BaseModel):
    source_type: str
    source_stream_id: str
    source_stream_name: str | None = None
    source_message_id: str
    message_timestamp_utc: datetime
    raw_text: str
    raw_entities_if_available: Any | None = None
    forwarded_from_if_available: str | None = None


class ExtractionEntities(BaseModel):
    countries: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)


class MarketStat(BaseModel):
    label: str
    value: float
    unit: str
    context: str | None = None


class ExtractionTag(BaseModel):
    tag_type: str
    tag_value: str
    tag_source: str = "observed"
    confidence: float | None = None

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
        return v


class ExtractionRelation(BaseModel):
    subject_type: str
    subject_value: str
    relation_type: str
    object_type: str
    object_value: str
    relation_source: str = "observed"
    inference_level: int | None = None
    confidence: float | None = None

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
        return v


class ExtractionImpactInputs(BaseModel):
    severity_cues: list[str] = Field(default_factory=list)
    economic_relevance_cues: list[str] = Field(default_factory=list)
    propagation_potential_cues: list[str] = Field(default_factory=list)
    specificity_cues: list[str] = Field(default_factory=list)
    novelty_cues: list[str] = Field(default_factory=list)
    strategic_tag_hits: list[str] = Field(default_factory=list)


class ExtractionJson(BaseModel):
    topic: Topic
    event_type: str | None = None
    directionality: str | None = None
    entities: ExtractionEntities
    affected_countries_first_order: list[str] = Field(default_factory=list)
    market_stats: list[MarketStat] = Field(default_factory=list)
    tags: list[ExtractionTag] = Field(default_factory=list)
    relations: list[ExtractionRelation] = Field(default_factory=list)
    impact_inputs: ExtractionImpactInputs = Field(default_factory=ExtractionImpactInputs)
    sentiment: Sentiment = "unknown"
    confidence: float = 0.0
    impact_score: float = 0.0
    is_breaking: bool = False
    breaking_window: BreakingWindow = "none"
    event_time: datetime | None = None
    source_claimed: str | None = None
    summary_1_sentence: str
    keywords: list[str] = Field(default_factory=list)
    event_core: str | None = None
    event_fingerprint: str = ""

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
        return v

    @field_validator("impact_score")
    @classmethod
    def _validate_impact_score(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError("impact_score must be between 0 and 100")
        return v


class RoutingDecisionData(BaseModel):
    store_to: list[str]
    publish_priority: PublishPriority
    requires_evidence: bool
    event_action: EventAction
    triage_action: Literal["archive", "monitor", "update", "promote"] | None = None
    triage_rules: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    rules_fired: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class IngestResponse(BaseModel):
    status: Literal["created", "duplicate"]
    raw_message_id: int
    event_id: int | None = None
    event_action: EventAction | None = None


class EvidenceSource(BaseModel):
    publisher: str
    title: str
    url: HttpUrl
    published_time: datetime | None = None
    snippet: str


class FeedEventItem(BaseModel):
    id: int
    summary: str
    topic: Topic
    event_time: str
    impact_score: int


class FeedEventsResponse(BaseModel):
    items: list[FeedEventItem]
    next_cursor: str | None


class ThemeRunTriggerRequest(BaseModel):
    theme_key: str
    cadence: Literal["daily", "weekly"] = "daily"
    window_start_utc: datetime | None = None
    window_end_utc: datetime | None = None
    dry_run: bool = False
    emit_brief: bool = True


class ThemeBatchRunResponse(BaseModel):
    run_id: int
    run_key: str
    theme_key: str
    cadence: Literal["daily", "weekly"]
    window_start_utc: datetime
    window_end_utc: datetime
    status: str
    evidence_count: int
    assessments_created: int
    cards_created: int
    emitted_cards: int
    suppressed_cards: int
    brief_status: str
    error_message: str | None = None


class ThemeDefinitionResponse(BaseModel):
    key: str
    title: str
    supported_cadences: list[str]
    lenses: list[str]
    allowed_transmission_patterns: list[str]
    relevant_event_archetypes: list[str]


class ThemeRunItemResponse(BaseModel):
    id: int
    run_key: str
    theme_key: str
    cadence: str
    window_start_utc: datetime
    window_end_utc: datetime
    status: str
    selected_evidence_count: int
    assessment_count: int
    thesis_card_count: int
    suppressed_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None


class ThemeAssessmentResponse(BaseModel):
    id: int
    stable_key: str
    theme_key: str
    cadence: str
    window_start_utc: datetime
    window_end_utc: datetime
    active_lenses: list[str]
    active_transmission_patterns: list[str]
    primary_lens: str | None
    primary_transmission_pattern: str | None
    evidence_summary: dict[str, Any]
    top_supporting_evidence_ids: list[int]
    top_contradictory_evidence_ids: list[int]
    dominant_drivers: dict[str, Any]
    transmission_narrative: dict[str, Any]
    candidate_opportunities: list[str]
    candidate_risks: list[str]
    evidence_strength_score: float
    lens_fit_score: float
    opportunity_priority_score: float
    confidence_score: float
    urgency: str
    time_horizon: str
    invalidation_conditions: list[str]
    status: str
    created_at: datetime


class ThesisCardResponse(BaseModel):
    id: int
    assessment_id: int
    theme_key: str
    cadence: str
    title: str
    what_happened: str
    why_it_matters: str
    transmission_path: str
    opportunity_angles: list[str]
    confidence: float
    what_to_watch_next: str
    invalidation_criteria: str
    supporting_evidence_refs: list[int]
    status: str
    suppression_reason: str | None
    material_update_reason: str | None
    created_at: datetime


class ThemeBriefResponse(BaseModel):
    id: int
    theme_run_id: int
    theme_key: str
    cadence: str
    window_start_utc: datetime
    window_end_utc: datetime
    summary_text: str
    highlights: list[str]
    assessment_ids: list[int]
    thesis_card_ids: list[int]
    status: str
    created_at: datetime

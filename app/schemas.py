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


class ExtractionJson(BaseModel):
    topic: Topic
    entities: ExtractionEntities
    affected_countries_first_order: list[str] = Field(default_factory=list)
    market_stats: list[MarketStat] = Field(default_factory=list)
    sentiment: Sentiment = "unknown"
    confidence: float = 0.0
    impact_score: float = 0.0
    is_breaking: bool = False
    breaking_window: BreakingWindow = "none"
    event_time: datetime | None = None
    source_claimed: str | None = None
    summary_1_sentence: str
    keywords: list[str] = Field(default_factory=list)
    event_fingerprint: str

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


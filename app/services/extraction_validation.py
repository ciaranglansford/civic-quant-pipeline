from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from ..schemas import ExtractionEntities, MarketStat


class StrictExtractionJson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    entities: ExtractionEntities
    affected_countries_first_order: list[str]
    market_stats: list[MarketStat]
    sentiment: str
    confidence: float
    impact_score: float
    is_breaking: bool
    breaking_window: str
    event_time: str | None
    source_claimed: str | None
    summary_1_sentence: str
    keywords: list[str]
    event_fingerprint: str


class ExtractionValidationError(ValueError):
    pass


def parse_and_validate_extraction(raw_text: str) -> dict:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ExtractionValidationError(f"invalid_json: {e.msg}") from e

    if not isinstance(payload, dict):
        raise ExtractionValidationError("invalid_json: root must be object")

    try:
        strict_obj = StrictExtractionJson.model_validate(payload)
    except ValidationError as e:
        raise ExtractionValidationError(f"schema_error: {e.errors()[0]['msg']}") from e

    from ..schemas import ExtractionJson

    try:
        model = ExtractionJson.model_validate(strict_obj.model_dump())
    except ValidationError as e:
        raise ExtractionValidationError(f"schema_error: {e.errors()[0]['msg']}") from e
    return model.model_dump(mode="json")

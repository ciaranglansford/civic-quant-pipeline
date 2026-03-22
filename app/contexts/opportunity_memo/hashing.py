from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from .contracts import OpportunityMemoStructuredArtifact


def _stable_hash(value: dict[str, Any]) -> str:
    canonical_json = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def input_hash_for_opportunity_memo(
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
    selected_topic: str,
    selected_event_ids: list[int],
    selected_primary_driver: dict[str, Any],
    generation_settings: dict[str, Any],
) -> str:
    payload = {
        "window": {
            "start_utc": window_start_utc.isoformat(),
            "end_utc": window_end_utc.isoformat(),
        },
        "selected_topic": selected_topic,
        "selected_event_ids": [int(value) for value in selected_event_ids],
        "selected_primary_driver": selected_primary_driver,
        "generation_settings": generation_settings,
    }
    return _stable_hash(payload)


def canonical_hash_for_opportunity_memo(
    *,
    memo: OpportunityMemoStructuredArtifact,
) -> str:
    payload = memo.model_dump(mode="json")
    return _stable_hash(payload)

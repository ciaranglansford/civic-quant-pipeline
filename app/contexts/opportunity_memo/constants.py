from __future__ import annotations

from typing import Final


OPPORTUNITY_TOPICS: Final[list[str]] = [
    "natural_gas",
    "lng",
    "oil",
    "fertilizers",
    "grains",
    "power",
    "shipping",
    "carbon",
    "coal",
]

TOPIC_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "natural_gas": (
        "natural gas",
        "gas",
        "henry hub",
        "ttf",
        "pipeline gas",
    ),
    "lng": (
        "lng",
        "liquefied natural gas",
        "regasification",
    ),
    "oil": (
        "oil",
        "crude",
        "brent",
        "wti",
        "diesel",
        "naphtha",
    ),
    "fertilizers": (
        "fertilizer",
        "fertiliser",
        "ammonia",
        "urea",
        "potash",
        "dap",
        "map",
    ),
    "grains": (
        "grain",
        "grains",
        "wheat",
        "corn",
        "maize",
        "soy",
        "soybean",
        "barley",
        "rice",
    ),
    "power": (
        "power",
        "electricity",
        "grid",
        "generation",
        "utility",
        "baseload",
    ),
    "shipping": (
        "shipping",
        "freight",
        "vessel",
        "tanker",
        "port",
        "transit",
        "route",
        "logistics",
    ),
    "carbon": (
        "carbon",
        "co2",
        "emissions",
        "allowance",
        "ets",
        "cbam",
        "offset",
    ),
    "coal": (
        "coal",
        "thermal coal",
        "coking coal",
    ),
}

TOPIC_KEYWORD_ORDER: Final[dict[str, int]] = {
    topic: idx for idx, topic in enumerate(OPPORTUNITY_TOPICS)
}

DRIVER_KEYS: Final[tuple[str, ...]] = (
    "supply_disruption",
    "demand_acceleration",
    "inventory_shift",
    "policy_change",
    "trade_flow_repricing",
    "weather_shock",
    "input_cost_pressure",
)

TOPIC_SCORE_WEIGHTS: Final[dict[str, float]] = {
    "normalized_event_count": 0.30,
    "normalized_weighted_impact": 0.25,
    "normalized_novelty": 0.20,
    "normalized_coherence": 0.15,
    "normalized_actionability": 0.10,
}

DRIVER_SCORE_WEIGHTS: Final[dict[str, float]] = {
    "supporting_event_weight": 0.40,
    "temporal_density": 0.25,
    "entity_consistency": 0.20,
    "external_confirmability": 0.15,
}

TOPIC_SELECTION_THRESHOLD_DEFAULT: Final[float] = 0.58
MIN_SUPPORTING_EVENTS_DEFAULT: Final[int] = 3
MIN_EXTERNAL_SOURCES_DEFAULT: Final[int] = 3

TRACEABILITY_REQUIRED_SECTION_KEYS: Final[set[str]] = {
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
}

OPTIONAL_LIGHT_TRACEABILITY_SECTION_KEYS: Final[set[str]] = {
    "opportunity_target",
}

RUN_STATUS_RUNNING: Final[str] = "running"
RUN_STATUS_NO_TOPIC_FOUND: Final[str] = "no_topic_found"
RUN_STATUS_VALIDATION_FAILED: Final[str] = "validation_failed"
RUN_STATUS_COMPLETED: Final[str] = "completed"
RUN_STATUS_DELIVERY_FAILED: Final[str] = "delivery_failed"

MEMO_SELECTION_MODE_AUTO: Final[str] = "auto"
MEMO_SELECTION_MODE_MANUAL: Final[str] = "manual"

MEMO_DESTINATION_TELEGRAM: Final[str] = "vip_telegram"

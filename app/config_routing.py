from __future__ import annotations

from dataclasses import dataclass

from .schemas import PublishPriority, Topic


@dataclass(frozen=True)
class RoutingConfig:
    topic_destinations: dict[Topic, list[str]]
    impact_priority_thresholds: list[tuple[float, PublishPriority]]
    evidence_enabled: bool = False


DEFAULT_ROUTING_CONFIG = RoutingConfig(
    topic_destinations={
        "macro_econ": ["macro_events"],
        "central_banks": ["macro_events"],
        "equities": ["stocks_events"],
        "credit": ["credit_events"],
        "rates": ["macro_events"],
        "fx": ["macro_events"],
        "commodities": ["macro_events"],
        "crypto": ["crypto_events"],
        "war_security": ["war_security_events"],
        "geopolitics": ["war_security_events"],
        "company_specific": ["stocks_events"],
        "other": ["other_events"],
    },
    # Ordered high -> low
    impact_priority_thresholds=[
        (80.0, "high"),
        (60.0, "medium"),
        (30.0, "low"),
        (0.0, "none"),
    ],
    evidence_enabled=False,
)


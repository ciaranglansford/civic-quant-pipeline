from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..models import Event


_TOPIC_LABELS: dict[str, str] = {
    "macro_econ": "Macro Econ",
    "central_banks": "Central Banks",
    "equities": "Equities",
    "credit": "Credit",
    "rates": "Rates",
    "fx": "FX",
    "commodities": "Commodities",
    "crypto": "Crypto",
    "war_security": "War / Security",
    "geopolitics": "Geopolitics",
    "company_specific": "Company Specific",
    "other": "Other",
}


def _topic_label(topic: str | None) -> str:
    if not topic:
        return "Other"
    return _TOPIC_LABELS.get(topic, topic)


def build_digest(events: list[Event], window_hours: int) -> str:
    by_topic: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        by_topic[_topic_label(e.topic)].append(e)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append(f"Civicquant Digest — last {window_hours}h (generated {now})")
    lines.append("")

    counts = ", ".join(f"{topic}: {len(items)}" for topic, items in sorted(by_topic.items()))
    lines.append(f"Counts: {counts}" if counts else "Counts: 0")
    lines.append("")

    for topic in sorted(by_topic.keys()):
        lines.append(f"== {topic} ==")
        for e in by_topic[topic]:
            summary = (e.summary_1_sentence or "").strip() or "(no summary)"
            corroboration = "unknown"
            lines.append(f"- {summary} (impact={e.impact_score if e.impact_score is not None else 'n/a'}, corroboration={corroboration})")
        lines.append("")

    lines.append("Note: informational only; no investment advice. Uncorroborated items may be included and are labeled accordingly.")
    return "\n".join(lines).strip() + "\n"


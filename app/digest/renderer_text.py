from __future__ import annotations

from .types import CanonicalDigest


def _format_utc(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def render_canonical_text(digest: CanonicalDigest) -> str:
    lines: list[str] = []
    lines.append(f"Window {_format_utc(digest.window.start_utc)} to {_format_utc(digest.window.end_utc)}")
    lines.append(f"Events: {digest.total_events}")
    counts = ", ".join(f"{section.topic_label}: {section.item_count}" for section in digest.sections)
    lines.append(f"Counts: {counts}" if counts else "Counts: 0")
    lines.append("")

    for section in digest.sections:
        lines.append(f"== {section.topic_label} ==")
        for item in section.items:
            lines.append(f"- {item.summary_1_sentence}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"

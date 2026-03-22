from __future__ import annotations

import html
import re
from datetime import datetime

from .contracts import OpportunityMemoStructuredArtifact


_WS_RE = re.compile(r"\s+")


def _clean(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def render_opportunity_memo_markdown(
    *,
    memo: OpportunityMemoStructuredArtifact,
    topic: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> str:
    lines: list[str] = []
    lines.append(f"# {memo.title}")
    lines.append("")
    lines.append(f"Topic: {topic}")
    lines.append(
        f"Window (UTC): {window_start_utc.isoformat()} -> {window_end_utc.isoformat()} (half-open)"
    )
    lines.append("")
    lines.append("## Thesis")
    lines.append(_clean(memo.thesis))
    lines.append("")
    lines.append("## Opportunity Target")
    lines.append(_clean(memo.opportunity_target))
    lines.append("")
    lines.append("## Background")
    lines.append(_clean(memo.background))
    lines.append("")
    lines.append("## Primary Driver")
    lines.append(_clean(memo.primary_driver))
    lines.append("")
    lines.append("## Supporting Developments")
    for row in memo.supporting_developments:
        lines.append(f"- {_clean(row)}")
    lines.append("")
    lines.append("## Why Now")
    lines.append(_clean(memo.why_now))
    lines.append("")
    lines.append("## Action Path")
    lines.append(_clean(memo.action_path))
    lines.append("")
    lines.append("## Risks")
    for row in memo.risks:
        lines.append(f"- {_clean(row)}")
    lines.append("")
    lines.append("## Watchpoints")
    for row in memo.watchpoints:
        lines.append(f"- {_clean(row)}")
    lines.append("")
    lines.append("## Conclusion")
    lines.append(_clean(memo.conclusion))
    return "\n".join(lines).strip()


def render_opportunity_memo_telegram_html(
    *,
    memo: OpportunityMemoStructuredArtifact,
    topic: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> str:
    lines: list[str] = []
    lines.append("<b>Opportunity Memo</b>")
    lines.append("")
    lines.append(f"<b>{html.escape(_clean(memo.title))}</b>")
    lines.append(
        f"<i>Topic: {html.escape(topic)} | Window: {html.escape(window_start_utc.strftime('%Y-%m-%d %H:%M'))}"
        f" to {html.escape(window_end_utc.strftime('%Y-%m-%d %H:%M'))} UTC</i>"
    )

    def _section(title: str, body: str) -> None:
        lines.append("")
        lines.append(f"<b>{html.escape(title)}</b>")
        lines.append(html.escape(_clean(body)))

    def _section_list(title: str, rows: list[str]) -> None:
        lines.append("")
        lines.append(f"<b>{html.escape(title)}</b>")
        for row in rows:
            lines.append(f"- {html.escape(_clean(row))}")

    _section("Thesis", memo.thesis)
    _section("Opportunity Target", memo.opportunity_target)
    _section("Background", memo.background)
    _section("Primary Driver", memo.primary_driver)
    _section_list("Supporting Developments", memo.supporting_developments)
    _section("Why Now", memo.why_now)
    _section("Action Path", memo.action_path)
    _section_list("Risks", memo.risks)
    _section_list("Watchpoints", memo.watchpoints)
    _section("Conclusion", memo.conclusion)

    lines.append("")
    lines.append("<i>- Not investment advice.</i>")
    return "\n".join(lines).strip()

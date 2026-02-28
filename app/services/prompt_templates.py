from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROMPT_VERSION = "extraction_agent_v2"
_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.txt"


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_version: str
    prompt_text: str


def render_extraction_prompt(
    *, normalized_text: str, message_time: datetime, source_channel_name: str | None
) -> RenderedPrompt:
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"missing prompt template: {_TEMPLATE_PATH}")

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = (
        template.replace("{{normalized_text}}", normalized_text)
        .replace("{{message_time}}", message_time.isoformat())
        .replace("{{source_channel_name}}", source_channel_name or "")
    )

    required = ("normalized_text", "message_time", "source_channel_name")
    missing = [k for k in required if f"{{{{{k}}}}}" in rendered]
    if missing:
        raise ValueError(f"template placeholders not replaced: {missing}")

    return RenderedPrompt(prompt_version=PROMPT_VERSION, prompt_text=rendered)

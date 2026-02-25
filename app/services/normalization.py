import re


_WS_RE = re.compile(r"\s+")


def normalize_message_text(raw_text: str) -> str:
    """
    Deterministic normalization intended for dedup/extraction stability.

    Constraints:
    - Preserve numbers, tickers, and units.
    - Reduce whitespace noise.
    """
    if raw_text is None:
        return ""
    text = raw_text.strip()
    text = _WS_RE.sub(" ", text)
    return text


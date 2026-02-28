import re


_WS_RE = re.compile(r"\s+")
_LEADING_MARKER_RE = re.compile(
    r"^(?:(?:\*+\s*)?(?:\u26a0\ufe0f|🚨|BREAKING:?|ALERT:?|URGENT:?|\[BREAKING\])\s*)+",
    flags=re.IGNORECASE,
)
_DATELINE_RE = re.compile(r"^[A-Z][A-Z .'-]{1,40}\s*\((?:AP|REUTERS|AFP|BLOOMBERG)\)\s*[—:-]\s*", flags=re.IGNORECASE)
_SOURCE_SUFFIX_RE = re.compile(r"\s*[-–—]\s*(?:AP|REUTERS|AFP|AXIOS|BLOOMBERG)\s*$", flags=re.IGNORECASE)
_PUNCT_REPEAT_RE = re.compile(r"([!?.,:;])\1+")


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
    text = _LEADING_MARKER_RE.sub("", text)
    text = _DATELINE_RE.sub("", text)
    text = _SOURCE_SUFFIX_RE.sub("", text)
    text = _PUNCT_REPEAT_RE.sub(r"\1", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


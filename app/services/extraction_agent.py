from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from ..schemas import ExtractionEntities, ExtractionJson, MarketStat, Topic


_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_NUMBER_RE = re.compile(r"(?<!\w)(\d+(?:\.\d+)?)(?:\s?)(bp|bps|%|bn|m|mm|b|k)?\b", re.IGNORECASE)


_TOPIC_HINTS: list[tuple[Topic, tuple[str, ...]]] = [
    ("macro_econ", ("cpi", "ppi", "gdp", "inflation", "payroll", "nfp", "pce", "unemployment", "retail sales")),
    ("central_banks", ("fed", "fomc", "ecb", "boj", "boe", "rate decision", "hike", "cut", "minutes")),
    ("credit", ("spread", "cds", "high yield", "investment grade", "default", "distressed", "tranche")),
    ("rates", ("ust", "treasury", "yields", "bps", "bp", "curve", "2y", "10y", "30y")),
    ("fx", ("usd", "eur", "jpy", "gbp", "fx", "dxy")),
    ("commodities", ("oil", "brent", "wti", "gold", "silver", "copper", "gas", "opec")),
    ("crypto", ("btc", "bitcoin", "eth", "ethereum", "crypto", "stablecoin")),
    ("war_security", ("pentagon", "nato", "strike", "attack", "missile", "defense", "troops")),
    ("geopolitics", ("sanctions", "diplomacy", "election", "border", "tariff", "embargo")),
]


@dataclass(frozen=True)
class ExtractionAgent:
    model_name: str = "stub-extractor-v1"

    def extract(self, normalized_text: str, message_time: datetime, source_channel_name: str | None) -> ExtractionJson:
        text = normalized_text or ""
        lowered = text.lower()

        topic: Topic = "other"
        for t, hints in _TOPIC_HINTS:
            if any(h in lowered for h in hints):
                topic = t
                break

        tickers = sorted(set(_TICKER_RE.findall(text)))[:20]
        numbers = [m.group(0) for m in _NUMBER_RE.finditer(text)]
        numbers_norm = [n.lower().replace(" ", "") for n in numbers]

        keywords = []
        if source_channel_name:
            keywords.append(source_channel_name)
        keywords.extend(tickers[:10])
        keywords.extend(numbers_norm[:10])

        summary = text[:240].strip()
        if len(text) > 240:
            summary = summary.rstrip(".") + "…"
        if not summary:
            summary = "No text content."

        # Event time falls back to message time in Phase 1.
        if message_time.tzinfo is None:
            event_time = message_time.replace(tzinfo=None)
        else:
            event_time = message_time.astimezone(timezone.utc).replace(tzinfo=None)

        # Lightweight market_stats stub: capture up to 3 numeric facts.
        market_stats: list[MarketStat] = []
        for raw in numbers_norm[:3]:
            # Parse best-effort: value and unit.
            m = _NUMBER_RE.search(raw)
            if not m:
                continue
            value = float(m.group(1))
            unit = (m.group(2) or "").lower() or "value"
            market_stats.append(MarketStat(label="reported", value=value, unit=unit, context=None))

        entities = ExtractionEntities(
            countries=[],
            orgs=[],
            people=[],
            tickers=tickers,
        )

        # Impact heuristic: more numbers/tickers implies slightly higher impact.
        impact = min(100.0, float(len(numbers_norm) * 8 + len(tickers) * 3))
        confidence = 0.4 if text else 0.1
        is_breaking = impact >= 60.0
        breaking_window = "1h" if is_breaking else "none"

        fingerprint_source = "|".join(
            [
                topic,
                (source_channel_name or "").lower(),
                ",".join(tickers).lower(),
                ",".join(numbers_norm),
            ]
        )
        event_fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:48]

        return ExtractionJson(
            topic=topic,
            entities=entities,
            affected_countries_first_order=[],
            market_stats=market_stats,
            sentiment="unknown",
            confidence=confidence,
            impact_score=impact,
            is_breaking=is_breaking,
            breaking_window=breaking_window,
            event_time=event_time,
            source_claimed=None,
            summary_1_sentence=summary,
            keywords=keywords,
            event_fingerprint=event_fingerprint,
        )


from __future__ import annotations

from datetime import datetime, timedelta

from app.config import Settings
from app.digest.adapters.telegram import TelegramDigestAdapter, _top_developments
from app.digest.adapters.x_placeholder import XPlaceholderDigestAdapter
from app.digest.orchestrator import _default_adapters
from app.digest.types import CanonicalDigest, DigestItem, DigestWindow, TopicSection


def _sample_digest() -> CanonicalDigest:
    now = datetime(2026, 1, 1, 0, 0, 0)
    window = DigestWindow(
        start_utc=now,
        end_utc=now + timedelta(hours=4),
        hours=4,
    )
    item = DigestItem(
        event_id=1,
        topic_raw="fx",
        topic_label="FX",
        summary_1_sentence="Sample summary",
        impact_score=12.0,
        corroboration="unknown",
        last_updated_at=now + timedelta(minutes=5),
    )
    section = TopicSection(topic_label="FX", items=(item,))
    return CanonicalDigest(window=window, sections=(section,), event_ids=(1,))


def test_telegram_adapter_only_transports_payload_not_digest_semantics():
    digest = _sample_digest()
    canonical_text = "canonical text payload\n"
    adapter = TelegramDigestAdapter(settings=Settings())

    payload = adapter.render_payload(digest, canonical_text)
    assert payload != canonical_text
    assert "<b>News Digest</b>" in payload
    assert "<i>Window:" in payload
    assert "<i>Events: 1</i>" in payload
    assert "<i>Topics: FX 1</i>" in payload
    assert "<b>Top developments</b>" in payload
    assert "<b>FX</b>" in payload
    assert "- Sample summary" in payload
    assert "<i>- Not investment advice.</i>" in payload


def test_telegram_top_developments_is_deterministic_by_update_time_then_id():
    now = datetime(2026, 1, 1, 0, 0, 0)
    digest = CanonicalDigest(
        window=DigestWindow(start_utc=now, end_utc=now + timedelta(hours=4), hours=4),
        sections=(
            TopicSection(
                topic_label="A",
                items=(
                    DigestItem(
                        event_id=2,
                        topic_raw="a",
                        topic_label="A",
                        summary_1_sentence="older id2",
                        impact_score=31.0,
                        corroboration="unknown",
                        last_updated_at=now + timedelta(minutes=1),
                    ),
                    DigestItem(
                        event_id=1,
                        topic_raw="a",
                        topic_label="A",
                        summary_1_sentence="older id1",
                        impact_score=32.0,
                        corroboration="unknown",
                        last_updated_at=now + timedelta(minutes=1),
                    ),
                ),
            ),
            TopicSection(
                topic_label="B",
                items=(
                    DigestItem(
                        event_id=3,
                        topic_raw="b",
                        topic_label="B",
                        summary_1_sentence="newest",
                        impact_score=33.0,
                        corroboration="unknown",
                        last_updated_at=now + timedelta(minutes=2),
                    ),
                ),
            ),
        ),
        event_ids=(1, 2, 3),
    )

    top = _top_developments(digest, limit=3)
    assert [item.event_id for item in top] == [3, 1, 2]


def test_x_placeholder_adapter_is_deferred():
    digest = _sample_digest()
    adapter = XPlaceholderDigestAdapter()

    payload = adapter.render_payload(digest, "canonical text payload\n")
    result = adapter.publish(payload)

    assert payload == "canonical text payload\n"
    assert result.status == "deferred"
    assert "deferred" in (result.error or "").lower()


def test_default_adapter_registry_excludes_x_placeholder():
    adapters = _default_adapters(Settings(tg_bot_token="token", tg_vip_chat_id="chat"))
    destinations = [adapter.destination for adapter in adapters]

    assert "x" not in destinations
    assert destinations == ["vip_telegram"]

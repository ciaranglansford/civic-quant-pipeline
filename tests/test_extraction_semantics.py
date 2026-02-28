from __future__ import annotations

from datetime import datetime

from app.services.extraction_validation import parse_and_validate_extraction
from app.services.prompt_templates import render_extraction_prompt


def test_prompt_version_uses_v2_and_includes_claim_semantics():
    rendered = render_extraction_prompt(
        normalized_text='NEITHER IRAN NOR THE U.S. HAVE CONFIRMED THE REPORT.',
        message_time=datetime.utcnow(),
        source_channel_name="feed",
    )
    assert rendered.prompt_version == "extraction_agent_v2"
    assert "literal reported claim" in rendered.prompt_text.lower()
    assert "not convert reported claims into confirmed facts" in rendered.prompt_text.lower()


def test_validation_accepts_uncertain_reported_claim_shape():
    raw_json = (
        '{"topic":"geopolitics","entities":{"countries":["United States"],"orgs":["AP"],'
        '"people":[],"tickers":[]},"affected_countries_first_order":["United States"],'
        '"market_stats":[],"sentiment":"unknown","confidence":0.61,"impact_score":66,'
        '"is_breaking":true,"breaking_window":"1h","event_time":null,"source_claimed":"AP",'
        '"summary_1_sentence":"AP reports officials made an unconfirmed claim.",'
        '"keywords":["unconfirmed","reported"],"event_fingerprint":"f"}'
    )
    parsed = parse_and_validate_extraction(raw_json)
    assert parsed["confidence"] == 0.61
    assert parsed["impact_score"] == 66.0
    assert "unconfirmed claim" in parsed["summary_1_sentence"].lower()

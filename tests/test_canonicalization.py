from app.services.canonicalization import canonicalize_extraction


def test_canonicalization_normalizes_countries_tickers_and_fingerprint():
    payload = {
        "topic": "geopolitics",
        "entities": {
            "countries": ["U.S.", "uk", "United States"],
            "orgs": ["  white house ", "WHITE HOUSE"],
            "people": [" Donald  Trump "],
            "tickers": ["eur", " eur ", "DXY!"],
        },
        "affected_countries_first_order": ["usa", "U.K."],
        "market_stats": [],
        "sentiment": "neutral",
        "confidence": 0.7,
        "impact_score": 61.0,
        "is_breaking": False,
        "breaking_window": "none",
        "event_time": None,
        "source_claimed": "  AXIOS  ",
        "summary_1_sentence": "Officials report diplomatic talks.",
        "keywords": ["talks"],
        "event_fingerprint": "geopolitics|null|us,uk|org|person|EUR|k1,k2,k3|event core",
    }

    canonical, rules = canonicalize_extraction(payload)
    assert canonical.entities.countries == ["United Kingdom", "United States"]
    assert canonical.affected_countries_first_order == ["United Kingdom", "United States"]
    assert canonical.entities.tickers == ["DXY", "EUR"]
    assert canonical.source_claimed == "AXIOS"
    assert "event_fingerprint_country_normalization" in rules
    assert "|United Kingdom,United States|" in canonical.event_fingerprint


def test_summary_safety_rewrites_high_risk_without_attribution():
    payload = {
        "topic": "geopolitics",
        "entities": {
            "countries": ["United States"],
            "orgs": ["Defense Ministry"],
            "people": [],
            "tickers": [],
        },
        "affected_countries_first_order": [],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.85,
        "impact_score": 85.0,
        "is_breaking": True,
        "breaking_window": "15m",
        "event_time": None,
        "source_claimed": "Defense Ministry",
        "summary_1_sentence": "Missiles launched toward border positions.",
        "keywords": ["missile"],
        "event_fingerprint": "geopolitics|null|United States|org|||k|event",
    }

    canonical, rules = canonicalize_extraction(payload)
    assert canonical.summary_1_sentence.startswith("Defense Ministry said")
    assert "summary_high_risk_attribution_rewrite" in rules


def test_summary_pronoun_disambiguation_uses_existing_actor():
    payload = {
        "topic": "war_security",
        "entities": {
            "countries": ["United States"],
            "orgs": ["NATO"],
            "people": [],
            "tickers": [],
        },
        "affected_countries_first_order": [],
        "market_stats": [],
        "sentiment": "negative",
        "confidence": 0.8,
        "impact_score": 70.0,
        "is_breaking": True,
        "breaking_window": "15m",
        "event_time": None,
        "source_claimed": "NATO",
        "summary_1_sentence": "It warned of a growing threat.",
        "keywords": [],
        "event_fingerprint": "war_security|null|United States|org|||k|event",
    }

    canonical, rules = canonicalize_extraction(payload)
    assert canonical.summary_1_sentence.startswith("NATO warned")
    assert "summary_pronoun_disambiguated" in rules

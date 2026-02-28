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

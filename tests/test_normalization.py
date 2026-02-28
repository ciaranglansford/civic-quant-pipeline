from app.services.normalization import normalize_message_text


def test_normalization_cleans_wire_markers_and_suffixes():
    raw = "🚨 BREAKING: JERUSALEM (AP) - U.S. OFFICIAL SAYS STRIKE STARTED - REUTERS"
    out = normalize_message_text(raw)
    assert out == "U.S. OFFICIAL SAYS STRIKE STARTED"


def test_normalization_is_deterministic_and_preserves_uncertainty_language():
    raw = "  *ALERT*  NEITHER IRAN NOR THE U.S. HAVE CONFIRMED.   "
    first = normalize_message_text(raw)
    second = normalize_message_text(raw)
    assert first == second
    assert "NEITHER IRAN NOR THE U.S. HAVE CONFIRMED." in first

from app.schemas import ExtractionEntities, ExtractionJson
from app.services.triage_engine import compute_triage_action


def _extraction(*, impact: float, confidence: float, breaking: bool) -> ExtractionJson:
    return ExtractionJson(
        topic="macro_econ",
        entities=ExtractionEntities(countries=[], orgs=[], people=[], tickers=[]),
        affected_countries_first_order=[],
        market_stats=[],
        sentiment="neutral",
        confidence=confidence,
        impact_score=impact,
        is_breaking=breaking,
        breaking_window="1h" if breaking else "none",
        event_time=None,
        source_claimed=None,
        summary_1_sentence="Reported update.",
        keywords=[],
        event_fingerprint="f",
    )


def test_triage_archive_case():
    out = compute_triage_action(_extraction(impact=10.0, confidence=0.2, breaking=False))
    assert out.triage_action == "archive"


def test_triage_monitor_case():
    out = compute_triage_action(_extraction(impact=50.0, confidence=0.5, breaking=False))
    assert out.triage_action == "monitor"


def test_triage_update_with_existing_event():
    out = compute_triage_action(
        _extraction(impact=70.0, confidence=0.5, breaking=False),
        existing_event_id=123,
    )
    assert out.triage_action == "update"


def test_triage_promote_case():
    out = compute_triage_action(_extraction(impact=85.0, confidence=0.8, breaking=True))
    assert out.triage_action == "promote"

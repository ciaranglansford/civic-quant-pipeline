from app.schemas import ExtractionEntities, ExtractionJson
from app.services.triage_engine import CandidateEventContext, TriageContext, compute_triage_action


def _extraction(
    *,
    impact: float,
    confidence: float,
    breaking: bool,
    summary: str = "Reported update.",
    source_claimed: str | None = None,
    countries: list[str] | None = None,
    orgs: list[str] | None = None,
    people: list[str] | None = None,
    keywords: list[str] | None = None,
) -> ExtractionJson:
    return ExtractionJson(
        topic="macro_econ",
        entities=ExtractionEntities(
            countries=countries or [],
            orgs=orgs or [],
            people=people or [],
            tickers=[],
        ),
        affected_countries_first_order=[],
        market_stats=[],
        sentiment="neutral",
        confidence=confidence,
        impact_score=impact,
        is_breaking=breaking,
        breaking_window="1h" if breaking else "none",
        event_time=None,
        source_claimed=source_claimed,
        summary_1_sentence=summary,
        keywords=keywords or [],
        event_fingerprint="f",
    )


def test_triage_archive_case():
    out = compute_triage_action(_extraction(impact=10.0, confidence=0.2, breaking=False))
    assert out.triage_action == "archive"
    assert "triage:low_signal_archive" in out.reason_codes


def test_triage_new_event_promote_case():
    out = compute_triage_action(_extraction(impact=85.0, confidence=0.85, breaking=True))
    assert out.triage_action == "promote"
    assert "triage:new_event_promote" in out.reason_codes


def test_triage_update_with_existing_event_material_change():
    out = compute_triage_action(
        _extraction(
            impact=75.0,
            confidence=0.8,
            breaking=True,
            summary="Officials launched a strike.",
            source_claimed="Defense Ministry",
            countries=["United States", "United Kingdom"],
        ),
        context=TriageContext(
            existing_event_id=123,
            candidate_event=CandidateEventContext(
                impact_band="medium",
                entities={"country:united states"},
                summary_tags={"reaction"},
                source_class="commentary",
            ),
        ),
    )
    assert out.triage_action == "update"
    assert "triage:related_material_update" in out.reason_codes


def test_triage_repeat_low_delta_burst_caps():
    extraction = _extraction(
        impact=70.0,
        confidence=0.8,
        breaking=True,
        summary="Officials condemn the move.",
        source_claimed="commentary desk",
        countries=["United States"],
    )

    second = compute_triage_action(
        extraction,
        context=TriageContext(
            existing_event_id=123,
            candidate_event=CandidateEventContext(
                impact_band="high",
                entities={"country:united states"},
                summary_tags={"reaction"},
                source_class="commentary",
            ),
            burst_low_delta_prior_count=1,
        ),
    )
    third = compute_triage_action(
        extraction,
        context=TriageContext(
            existing_event_id=123,
            candidate_event=CandidateEventContext(
                impact_band="high",
                entities={"country:united states"},
                summary_tags={"reaction"},
                source_class="commentary",
            ),
            burst_low_delta_prior_count=2,
        ),
    )
    assert second.triage_action == "update"
    assert "triage:burst_cap_update" in second.reason_codes
    assert third.triage_action == "monitor"
    assert "triage:burst_cap_monitor" in third.reason_codes


def test_local_domestic_incident_downgrades_urgency():
    out = compute_triage_action(
        _extraction(
            impact=90.0,
            confidence=0.9,
            breaking=True,
            summary="Police report multiple people injured in Austin, TX incident.",
            source_claimed="local police",
            keywords=["incident", "injured"],
        )
    )
    assert out.triage_action == "monitor"
    assert "triage:local_incident_downgrade" in out.reason_codes

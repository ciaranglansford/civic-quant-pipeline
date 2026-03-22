from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.opportunity_memo import build_opportunity_memo_input_pack, rank_topic_candidates
from app.contexts.opportunity_memo.contracts import (
    ExternalEvidencePack,
    ExternalEvidenceSource,
    OpportunityMemoInputPack,
    OpportunityMemoStructuredArtifact,
)
from app.contexts.opportunity_memo.ranking import rank_topic_opportunities
from app.contexts.opportunity_memo.research import _normalize_sources
from app.contexts.opportunity_memo.topic_mapping import map_event_to_topic
from app.contexts.opportunity_memo.validator import validate_opportunity_memo
from app.contexts.opportunity_memo.renderer import render_opportunity_memo_telegram_html
from app.db import Base
from app.models import Event, EventRelation, EventTag, Extraction, RawMessage


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True), engine


def _seed_event(
    db,
    *,
    msg_id: str,
    event_time: datetime,
    summary: str,
    impact_score: float,
    raw_text: str,
    payload_topic: str,
    payload_keywords: list[str],
    tags: list[tuple[str, str]],
    relations: list[tuple[str, str, str]],
):
    raw = RawMessage(
        source_channel_id="seed",
        source_channel_name="seed",
        telegram_message_id=msg_id,
        message_timestamp_utc=event_time,
        raw_text=raw_text,
        normalized_text=raw_text.lower(),
    )
    db.add(raw)
    db.flush()

    payload = {
        "topic": payload_topic,
        "summary_1_sentence": summary,
        "keywords": payload_keywords,
        "entities": {
            "countries": ["Qatar"],
            "orgs": ["Terminal Operator"],
            "people": [],
            "tickers": ["TTF"],
        },
        "market_stats": [{"label": "price", "value": 2.2, "unit": "%", "context": "up"}],
    }
    extraction = Extraction(
        raw_message_id=raw.id,
        extractor_name="extract-and-score-openai-v1",
        schema_version=1,
        event_time=event_time,
        topic=payload_topic,
        impact_score=impact_score,
        confidence=0.9,
        sentiment="negative",
        is_breaking=True,
        breaking_window="1h",
        event_fingerprint=f"fp-{msg_id}",
        event_identity_fingerprint_v2=f"fp-{msg_id}",
        payload_json=payload,
        canonical_payload_json=payload,
        metadata_json={"impact_scoring": {"calibrated_score": impact_score}},
        claim_hash=f"claim-{msg_id}",
    )
    db.add(extraction)
    db.flush()

    event = Event(
        event_fingerprint=f"event-{msg_id}",
        event_identity_fingerprint_v2=f"event-{msg_id}",
        topic=payload_topic,
        summary_1_sentence=summary,
        impact_score=impact_score,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        last_updated_at=event_time,
        latest_extraction_id=extraction.id,
        claim_hash=f"claim-{msg_id}",
    )
    db.add(event)
    db.flush()

    for tag_type, tag_value in tags:
        db.add(
            EventTag(
                event_id=event.id,
                tag_type=tag_type,
                tag_value=tag_value,
                tag_source="observed",
                confidence=0.9,
            )
        )
    for relation_type, subject_value, object_value in relations:
        db.add(
            EventRelation(
                event_id=event.id,
                subject_type="country",
                subject_value=subject_value,
                relation_type=relation_type,
                object_type="commodity",
                object_value=object_value,
                relation_source="observed",
                inference_level=0,
                confidence=0.8,
            )
        )
    db.flush()
    return event


def _valid_memo() -> OpportunityMemoStructuredArtifact:
    return OpportunityMemoStructuredArtifact.model_validate(
        {
            "title": "Natural Gas Supply Disruption Opportunity",
            "thesis": "Natural gas disruptions are sustaining a tradable tightening regime.",
            "opportunity_target": "Near-term gas-linked pricing and spread positioning.",
            "background": "A cluster of high-impact natural gas events points to persistent supply friction.",
            "primary_driver": "Natural gas supply disruption across key LNG-linked infrastructure remains the central driver.",
            "supporting_developments": [
                "Export curtailment signals and logistics constraints have stacked in the same window.",
                "Spot and forward market narratives are repricing around reduced flexibility.",
            ],
            "why_now": "Natural gas event density and recency indicate the repricing window is currently open.",
            "action_path": "Allocate risk through defined gas-exposure structures, prioritize liquid instruments, and rebalance position sizing as watchpoints update.",
            "risks": [
                "A rapid restart of constrained supply nodes could compress the thesis window.",
                "Policy intervention could cap pass-through and flatten expected spreads.",
            ],
            "watchpoints": [
                "Official outage/repair timelines from major LNG infrastructure.",
                "Shipping and storage indicators that confirm or reject tightening persistence.",
            ],
            "conclusion": "The setup is actionable if execution remains disciplined around invalidation conditions.",
            "traceability": {
                "paragraph_sources": [
                    {"paragraph_key": "thesis", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
                    {"paragraph_key": "background", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
                    {"paragraph_key": "primary_driver", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
                    {"paragraph_key": "supporting_developments[0]", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
                    {"paragraph_key": "supporting_developments[1]", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
                    {"paragraph_key": "why_now", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
                    {"paragraph_key": "action_path", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
                    {"paragraph_key": "risks[0]", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
                    {"paragraph_key": "risks[1]", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
                    {"paragraph_key": "watchpoints[0]", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
                    {"paragraph_key": "watchpoints[1]", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
                    {"paragraph_key": "conclusion", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
                    {"paragraph_key": "opportunity_target", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
                ]
            },
        }
    )


def test_topic_mapping_precedence_and_reason_trail():
    from_tags = map_event_to_topic(
        event_id=101,
        tags=[{"tag_type": "commodities", "tag_value": "Oil"}],
        relations=[
            {
                "relation_type": "curtails",
                "subject_value": "Qatar",
                "object_value": "Natural Gas",
            }
        ],
        latest_extraction_payload={
            "topic": "commodities",
            "keywords": ["natural gas", "shipping"],
        },
    )
    assert from_tags.topic == "oil"
    assert from_tags.diagnostics.source_layer == "event_tags"
    assert any(field.startswith("event_tags.") for field in from_tags.diagnostics.matched_fields)
    assert "precedence:event_tags" in from_tags.diagnostics.reason_trail

    from_relations = map_event_to_topic(
        event_id=102,
        tags=[],
        relations=[
            {
                "relation_type": "disrupts_logistics_of",
                "subject_value": "Canal",
                "object_value": "Shipping",
            }
        ],
        latest_extraction_payload={
            "topic": "commodities",
            "keywords": ["natural gas"],
        },
    )
    assert from_relations.topic == "shipping"
    assert from_relations.diagnostics.source_layer == "event_relations"
    assert any(field.startswith("event_relations.") for field in from_relations.diagnostics.matched_fields)
    assert "precedence:event_relations" in from_relations.diagnostics.reason_trail

    from_payload = map_event_to_topic(
        event_id=103,
        tags=[],
        relations=[],
        latest_extraction_payload={
            "topic": "commodities",
            "summary_1_sentence": "Natural gas supply remains tight.",
            "keywords": ["natural gas", "supply"],
        },
    )
    assert from_payload.topic == "natural_gas"
    assert from_payload.diagnostics.source_layer == "latest_extraction_payload"
    assert any(field.startswith("latest_extraction_payload.") for field in from_payload.diagnostics.matched_fields)
    assert "precedence:latest_extraction_payload" in from_payload.diagnostics.reason_trail

    no_match = map_event_to_topic(
        event_id=104,
        tags=[],
        relations=[],
        latest_extraction_payload={"topic": "macro", "keywords": ["rates", "inflation"]},
    )
    assert no_match.topic is None
    assert no_match.diagnostics.source_layer == "no_match"
    assert no_match.diagnostics.final_topic is None
    assert no_match.diagnostics.reason_trail == ["precedence:no_match"]


def test_novelty_heuristic_uses_prior_equivalent_window_fingerprints():
    now = datetime.utcnow().replace(microsecond=0)

    current = [
        {
            "id": 1,
            "mapped_topic": "natural_gas",
            "impact_score": 80.0,
            "event_time": now - timedelta(hours=2),
            "last_updated_at": now - timedelta(hours=2),
            "event_identity_fingerprint_v2": "id-a",
            "claim_hash": "claim-a",
            "latest_extraction_payload": {},
            "tags": [],
            "relations": [],
        },
        {
            "id": 2,
            "mapped_topic": "natural_gas",
            "impact_score": 78.0,
            "event_time": now - timedelta(hours=1),
            "last_updated_at": now - timedelta(hours=1),
            "event_identity_fingerprint_v2": "id-b",
            "claim_hash": "claim-b",
            "latest_extraction_payload": {},
            "tags": [],
            "relations": [],
        },
    ]
    prior_overlap = [
        {
            "id": 10,
            "mapped_topic": "natural_gas",
            "impact_score": 60.0,
            "event_time": now - timedelta(days=1, hours=2),
            "last_updated_at": now - timedelta(days=1, hours=2),
            "event_identity_fingerprint_v2": "id-a",
            "claim_hash": "prior-a",
            "latest_extraction_payload": {},
            "tags": [],
            "relations": [],
        },
        {
            "id": 11,
            "mapped_topic": "natural_gas",
            "impact_score": 58.0,
            "event_time": now - timedelta(days=1, hours=1),
            "last_updated_at": now - timedelta(days=1, hours=1),
            "event_identity_fingerprint_v2": "id-b",
            "claim_hash": "prior-b",
            "latest_extraction_payload": {},
            "tags": [],
            "relations": [],
        },
    ]
    prior_non_overlap = [
        {
            "id": 20,
            "mapped_topic": "natural_gas",
            "impact_score": 60.0,
            "event_time": now - timedelta(days=1, hours=2),
            "last_updated_at": now - timedelta(days=1, hours=2),
            "event_identity_fingerprint_v2": "id-x",
            "claim_hash": "prior-x",
            "latest_extraction_payload": {},
            "tags": [],
            "relations": [],
        }
    ]

    ranked_overlap = rank_topic_opportunities(
        current_events=current,
        prior_events=prior_overlap,
        start_time=now - timedelta(hours=6),
        end_time=now,
        topic_universe=["natural_gas"],
        limit=1,
        recent_memo_topics=set(),
    )
    ranked_non_overlap = rank_topic_opportunities(
        current_events=current,
        prior_events=prior_non_overlap,
        start_time=now - timedelta(hours=6),
        end_time=now,
        topic_universe=["natural_gas"],
        limit=1,
        recent_memo_topics=set(),
    )
    ranked_with_recent_penalty = rank_topic_opportunities(
        current_events=current,
        prior_events=prior_non_overlap,
        start_time=now - timedelta(hours=6),
        end_time=now,
        topic_universe=["natural_gas"],
        limit=1,
        recent_memo_topics={"natural_gas"},
    )

    assert ranked_overlap[0].novelty < ranked_non_overlap[0].novelty
    assert ranked_with_recent_penalty[0].novelty < ranked_non_overlap[0].novelty


def test_external_evidence_normalization_contract_shape():
    payload = {
        "sources": [
            {
                "source_id": "src_custom",
                "source_type": "web",
                "title": "Market Context",
                "publisher": "Example Publisher",
                "query": "",
                "summary": "Gas market context confirms tightening constraints.",
                "claim_support_tags": ["confirmation", "pricing"],
                "url": "https://example.com/context",
            },
            {
                "source_id": "src_drop",
                "source_type": "web",
                "title": "Empty Summary",
                "publisher": "Example Publisher",
                "query": "query 2",
                "summary": "",
                "claim_support_tags": [],
                "url": "https://example.com/empty",
            },
        ]
    }
    now = datetime.utcnow().replace(microsecond=0)
    normalized = _normalize_sources(
        raw_text=json.dumps(payload),
        retrieved_at=now,
        fallback_queries=["fallback_query_1", "fallback_query_2"],
    )

    assert len(normalized) == 1
    source = normalized[0]
    assert source.source_id == "src_custom"
    assert source.source_type == "web"
    assert source.title == "Market Context"
    assert source.publisher == "Example Publisher"
    assert source.retrieved_at == now
    assert source.query == "fallback_query_1"
    assert source.summary == "Gas market context confirms tightening constraints."
    assert source.claim_support_tags == ["confirmation", "pricing"]
    assert str(source.url) == "https://example.com/context"


def test_topic_ranking_is_deterministic_and_honors_topic_universe():
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            _seed_event(
                db,
                msg_id="a",
                event_time=now - timedelta(hours=3),
                summary="Natural gas outage cuts supply.",
                impact_score=85.0,
                raw_text="Coal headline noise",
                payload_topic="commodities",
                payload_keywords=["natural gas", "outage", "supply"],
                tags=[("commodities", "Natural Gas")],
                relations=[("curtails", "Qatar", "Natural Gas")],
            )
            _seed_event(
                db,
                msg_id="b",
                event_time=now - timedelta(hours=2),
                summary="LNG terminal restriction tightens gas flows.",
                impact_score=80.0,
                raw_text="Coal rumor",
                payload_topic="commodities",
                payload_keywords=["lng", "natural gas", "restriction"],
                tags=[("commodities", "Natural Gas")],
                relations=[("restricts_export_of", "Qatar", "LNG")],
            )
            _seed_event(
                db,
                msg_id="c",
                event_time=now - timedelta(hours=1),
                summary="Another gas disruption reinforces supply concerns.",
                impact_score=78.0,
                raw_text="Coal narrative",
                payload_topic="commodities",
                payload_keywords=["gas", "disruption", "supply"],
                tags=[("commodities", "Natural Gas")],
                relations=[("curtails", "Qatar", "Natural Gas")],
            )
            _seed_event(
                db,
                msg_id="d",
                event_time=now - timedelta(hours=1),
                summary="Oil prices drift higher on trade headlines.",
                impact_score=45.0,
                raw_text="Oil headline",
                payload_topic="commodities",
                payload_keywords=["oil", "trade"],
                tags=[("commodities", "Oil")],
                relations=[("supports", "Saudi Arabia", "Oil")],
            )
            db.commit()

            ranked_first = rank_topic_candidates(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic_universe=["natural_gas", "oil", "shipping"],
                limit=3,
                recent_memo_topics=set(),
            )
            ranked_second = rank_topic_candidates(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic_universe=["natural_gas", "oil", "shipping"],
                limit=3,
                recent_memo_topics=set(),
            )

            assert ranked_first[0].topic == "natural_gas"
            assert ranked_first[0].event_count >= 3
            assert [row.model_dump(mode="json") for row in ranked_first] == [
                row.model_dump(mode="json") for row in ranked_second
            ]

            oil_only = rank_topic_candidates(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic_universe=["oil"],
                limit=5,
                recent_memo_topics=set(),
            )
            assert len(oil_only) == 1
            assert oil_only[0].topic == "oil"
    finally:
        engine.dispose()


def test_topic_ranking_can_return_no_memo_worthy_topic_below_threshold():
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            ranked = rank_topic_candidates(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic_universe=["natural_gas", "oil"],
                limit=2,
                recent_memo_topics=set(),
            )
            assert ranked[0].topic_score < 0.58
    finally:
        engine.dispose()


def test_input_builder_uses_event_layer_and_selects_driver_deterministically():
    SessionLocal, engine = _session_factory()
    try:
        now = datetime.utcnow().replace(microsecond=0)
        with SessionLocal() as db:
            _seed_event(
                db,
                msg_id="x1",
                event_time=now - timedelta(hours=2),
                summary="Natural gas supply disruption persists.",
                impact_score=82.0,
                raw_text="Coal only rumor text should not drive mapping.",
                payload_topic="commodities",
                payload_keywords=["natural gas", "supply disruption", "price"],
                tags=[("commodities", "Natural Gas")],
                relations=[("curtails", "Qatar", "Natural Gas")],
            )
            _seed_event(
                db,
                msg_id="x2",
                event_time=now - timedelta(hours=1),
                summary="LNG outage raises gas volatility.",
                impact_score=79.0,
                raw_text="Unrelated grain chatter in raw text.",
                payload_topic="commodities",
                payload_keywords=["lng", "outage", "natural gas"],
                tags=[("commodities", "Natural Gas")],
                relations=[("restricts_export_of", "Qatar", "LNG")],
            )
            db.commit()

            pack_a, _rows_a = build_opportunity_memo_input_pack(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                topic_score=0.9,
                selection_reason="test",
                topic_breakdown={"normalized_event_count": 1.0},
            )
            pack_b, _rows_b = build_opportunity_memo_input_pack(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                topic_score=0.9,
                selection_reason="test",
                topic_breakdown={"normalized_event_count": 1.0},
            )

            assert len(pack_a.selected_event_ids) == 2
            assert [item.event_time for item in pack_a.event_timeline] == sorted(
                [item.event_time for item in pack_a.event_timeline]
            )
            assert pack_a.selected_primary_driver is not None
            assert pack_a.selected_primary_driver.driver_key == pack_b.selected_primary_driver.driver_key
            assert pack_a.selected_event_ids == pack_b.selected_event_ids
    finally:
        engine.dispose()


def test_validator_enforces_required_sections_traceability_and_topic_drift_rules():
    memo = _valid_memo()
    input_pack = OpportunityMemoInputPack.model_validate(
        {
            "topic": "natural_gas",
            "window": {
                "start_time": datetime.utcnow().isoformat(),
                "end_time": (datetime.utcnow() + timedelta(hours=6)).isoformat(),
            },
            "selected_event_ids": [1],
            "event_timeline": [
                {
                    "event_id": 1,
                    "event_time": datetime.utcnow().isoformat(),
                    "summary": "Gas disruption event.",
                    "impact_score": 80.0,
                    "entities": {},
                    "tags": [],
                    "relations": [],
                }
            ],
            "candidate_driver_groups": [],
            "selected_primary_driver": {
                "driver_key": "supply_disruption",
                "score": 0.8,
                "supporting_event_ids": [1],
                "score_components": {
                    "supporting_event_weight": 0.8,
                    "temporal_density": 0.7,
                    "entity_consistency": 0.6,
                    "external_confirmability": 0.5,
                },
            },
            "supporting_entities": [{"type": "commodity", "value": "natural_gas"}],
            "selection_diagnostics": {
                "topic_score": 0.75,
                "selection_reason": "test",
                "topic_breakdown": {},
            },
        }
    )
    external_pack = ExternalEvidencePack(
        topic="natural_gas",
        provider_name="test",
        sources=[
            ExternalEvidenceSource(
                source_id="src_01",
                source_type="web",
                title="S1",
                publisher="Pub1",
                retrieved_at=datetime.utcnow(),
                query="q1",
                summary="s1",
                claim_support_tags=["confirm"],
                url="https://example.com/1",
            ),
            ExternalEvidenceSource(
                source_id="src_02",
                source_type="web",
                title="S2",
                publisher="Pub2",
                retrieved_at=datetime.utcnow(),
                query="q2",
                summary="s2",
                claim_support_tags=["context"],
                url="https://example.com/2",
            ),
            ExternalEvidenceSource(
                source_id="src_03",
                source_type="web",
                title="S3",
                publisher="Pub3",
                retrieved_at=datetime.utcnow(),
                query="q3",
                summary="s3",
                claim_support_tags=["risk"],
                url="https://example.com/3",
            ),
        ],
    )

    passed = validate_opportunity_memo(
        memo=memo,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=1,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert passed.ok is True

    missing_section = memo.model_copy(update={"thesis": " "})
    failed_missing_section = validate_opportunity_memo(
        memo=missing_section,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=1,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert failed_missing_section.ok is False
    assert any(issue.code == "missing_required_section" for issue in failed_missing_section.errors)

    missing_traceability_payload = memo.model_dump(mode="json")
    missing_traceability_payload["traceability"] = {
        "paragraph_sources": [
            row.model_dump(mode="json")
            for row in memo.traceability.paragraph_sources
            if row.paragraph_key != "thesis"
        ]
    }
    missing_traceability = OpportunityMemoStructuredArtifact.model_validate(missing_traceability_payload)
    failed_trace = validate_opportunity_memo(
        memo=missing_traceability,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=1,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert failed_trace.ok is False
    assert any(issue.code == "missing_traceability" for issue in failed_trace.errors)

    drift_memo = memo.model_copy(
        update={
            "thesis": "Coal and shipping repricing dominate the current setup.",
            "background": "Coal and shipping disruptions dominate this multi-topic note.",
            "primary_driver": "Coal supply shock and shipping bottlenecks are the leading mechanism.",
            "supporting_developments": [
                "Coal benchmark rally accelerates.",
                "Shipping route bottlenecks reprice freight aggressively.",
            ],
            "why_now": "Coal and freight volatility are compounding in real time.",
        }
    )
    failed_drift = validate_opportunity_memo(
        memo=drift_memo,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=1,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert failed_drift.ok is False
    assert any(issue.code == "topic_drift_detected" for issue in failed_drift.errors)


def test_opportunity_memo_telegram_renderer_produces_memo_specific_payload():
    memo = _valid_memo()
    rendered = render_opportunity_memo_telegram_html(
        memo=memo,
        topic="natural_gas",
        window_start_utc=datetime(2026, 3, 15, 0, 0, 0),
        window_end_utc=datetime(2026, 3, 22, 0, 0, 0),
    )
    assert "<b>Opportunity Memo</b>" in rendered
    assert "<b>Thesis</b>" in rendered
    assert "<b>Action Path</b>" in rendered

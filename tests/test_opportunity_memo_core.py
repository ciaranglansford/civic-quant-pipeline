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
from app.contexts.opportunity_memo.renderer import render_opportunity_memo_telegram_html
from app.contexts.opportunity_memo.research import _normalize_sources
from app.contexts.opportunity_memo.topic_mapping import map_event_to_topic
from app.contexts.opportunity_memo.validator import validate_opportunity_memo
from app.contexts.opportunity_memo.writer import (
    _coerce_writer_payload,
    _harden_payload_with_deterministic_guards,
)
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
        "market_stats": [{"label": "price_move", "value": 2.2, "unit": "%", "context": "up"}],
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


def _base_input_pack() -> OpportunityMemoInputPack:
    return OpportunityMemoInputPack.model_validate(
        {
            "topic": "natural_gas",
            "window": {
                "start_time": datetime.utcnow().isoformat(),
                "end_time": (datetime.utcnow() + timedelta(hours=6)).isoformat(),
            },
            "selected_event_ids": [1, 2, 3],
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
                "supporting_event_ids": [1, 2],
                "score_components": {
                    "supporting_event_weight": 0.8,
                    "temporal_density": 0.7,
                    "entity_consistency": 0.6,
                    "external_confirmability": 0.5,
                },
            },
            "supporting_entities": [{"type": "commodity", "value": "natural_gas"}],
            "topic_event_stats": {
                "event_count": 3,
                "weighted_impact_score": 188.0,
                "average_impact_score": 79.5,
                "max_impact_score": 82.0,
                "recent_event_count": 2,
            },
            "driver_evidence_summary": {
                "driver_key": "supply_disruption",
                "supporting_event_count": 2,
                "supporting_event_share": 0.67,
                "supporting_event_ids": [1, 2],
            },
            "supporting_fact_candidates": [
                {
                    "fact_key": "event_1_summary",
                    "fact_text": "Event 1 impact score 80.0: Gas disruption event",
                    "internal_event_ids": [1],
                    "numeric_value": 80.0,
                    "unit": "impact_score",
                    "source_hint": "event_layer",
                }
            ],
            "selection_diagnostics": {
                "topic_score": 0.75,
                "selection_reason": "test",
                "topic_breakdown": {},
            },
        }
    )


def _external_pack() -> ExternalEvidencePack:
    return ExternalEvidencePack(
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
                summary="Storage fell 3.4% week-over-week in key hubs.",
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
                summary="Outage affected 6.2 mtpa equivalent export capacity.",
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
                summary="Regional spread widened 14% during the window.",
                claim_support_tags=["risk"],
                url="https://example.com/3",
            ),
        ],
    )


def _traceability_rows() -> list[dict]:
    return [
        {"paragraph_key": "core_thesis_one_liner", "internal_event_ids": [1, 2], "external_source_ids": ["src_01"]},
        {"paragraph_key": "market_setup", "internal_event_ids": [1, 2], "external_source_ids": ["src_01", "src_02"]},
        {"paragraph_key": "background", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
        {"paragraph_key": "primary_driver", "internal_event_ids": [1, 2], "external_source_ids": ["src_02"]},
        {"paragraph_key": "supporting_developments[0]", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        {"paragraph_key": "supporting_developments[1]", "internal_event_ids": [2], "external_source_ids": ["src_03"]},
        {"paragraph_key": "why_now", "internal_event_ids": [1, 2], "external_source_ids": ["src_01"]},
        {"paragraph_key": "why_this_is_an_opportunity", "internal_event_ids": [1, 2], "external_source_ids": ["src_03"]},
        {"paragraph_key": "trade_expression", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        {"paragraph_key": "quantified_evidence_points[0]", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
        {"paragraph_key": "quantified_evidence_points[1]", "internal_event_ids": [2], "external_source_ids": ["src_02"]},
        {"paragraph_key": "risks[0]", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
        {"paragraph_key": "risks[1]", "internal_event_ids": [2], "external_source_ids": ["src_02"]},
        {"paragraph_key": "invalidation_triggers[0]", "internal_event_ids": [2], "external_source_ids": ["src_03"]},
        {"paragraph_key": "invalidation_triggers[1]", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
        {"paragraph_key": "watchpoints[0]", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
        {"paragraph_key": "watchpoints[1]", "internal_event_ids": [2], "external_source_ids": ["src_02"]},
        {"paragraph_key": "conclusion", "internal_event_ids": [1, 2], "external_source_ids": ["src_03"]},
    ]


def _valid_memo() -> OpportunityMemoStructuredArtifact:
    return OpportunityMemoStructuredArtifact.model_validate(
        {
            "title": "Northwest Europe Gas Tightening Repricing Setup",
            "core_thesis_one_liner": "Northwest Europe gas spreads have upside repricing potential because supply-disruption signals tightened while storage fell in the same window.",
            "opportunity_target": "TTF front-month vs deferred spread and gas-sensitive utility hedge books in Northwest Europe.",
            "market_setup": "Event clustering shows synchronized supply friction and freight bottlenecks while regional storage and flow metrics deteriorated.",
            "background": "Three high-impact natural gas events within the window indicated repeated curtailment pressure and reduced balancing flexibility.",
            "primary_driver": "Deterministic driver selection identified supply_disruption with concentrated support across top-impact events.",
            "supporting_developments": [
                "Export flow constraints persisted across two linked terminals in the same 48-hour span.",
                "Forward curve steepened as balancing risk rose despite no broad demand collapse.",
            ],
            "why_now": "Within this window, event density accelerated and storage/freight datapoints confirmed timing-sensitive repricing pressure.",
            "why_this_is_an_opportunity": "The setup appears underappreciated because transmission from physical constraints to forward spread repricing has moved faster than consensus hedge positioning.",
            "trade_expression": "Express via liquid gas futures spread structures and optionality overlays tied to TTF curve steepening while sizing against invalidation triggers.",
            "quantified_evidence_points": [
                "Storage fell 3.4% week-over-week in monitored hubs during the memo window.",
                "A linked outage affected 6.2 mtpa equivalent export capacity and coincided with a 14% spread widening.",
            ],
            "risks": [
                "Fast supply restoration could compress spreads before positioning fully monetizes.",
                "Policy intervention on retail pass-through could dampen price transmission.",
            ],
            "invalidation_triggers": [
                "Confirmed restart of constrained export nodes ahead of published timelines.",
                "Two consecutive sessions of spread compression with normalized freight and storage draws.",
            ],
            "watchpoints": [
                "Terminal restart bulletins and verified load-port flow data.",
                "Storage trajectory updates and prompt-deferred spread behavior.",
            ],
            "confidence_level": "medium",
            "conclusion": "The opportunity is actionable while disruption-linked repricing persists and should be managed with explicit invalidation discipline.",
            "traceability": {"paragraph_sources": _traceability_rows()},
        }
    )


def test_topic_mapping_precedence_and_reason_trail():
    from_tags = map_event_to_topic(
        event_id=101,
        tags=[{"tag_type": "commodities", "tag_value": "Oil"}],
        relations=[{"relation_type": "curtails", "subject_value": "Qatar", "object_value": "Natural Gas"}],
        latest_extraction_payload={"topic": "commodities", "keywords": ["natural gas", "shipping"]},
    )
    assert from_tags.topic == "oil"
    assert from_tags.diagnostics.source_layer == "event_tags"
    assert "precedence:event_tags" in from_tags.diagnostics.reason_trail

    from_relations = map_event_to_topic(
        event_id=102,
        tags=[],
        relations=[{"relation_type": "disrupts_logistics_of", "subject_value": "Canal", "object_value": "Shipping"}],
        latest_extraction_payload={"topic": "commodities", "keywords": ["natural gas"]},
    )
    assert from_relations.topic == "shipping"
    assert from_relations.diagnostics.source_layer == "event_relations"

    from_payload = map_event_to_topic(
        event_id=103,
        tags=[],
        relations=[],
        latest_extraction_payload={"topic": "commodities", "summary_1_sentence": "Natural gas supply remains tight.", "keywords": ["natural gas", "supply"]},
    )
    assert from_payload.topic == "natural_gas"
    assert from_payload.diagnostics.source_layer == "latest_extraction_payload"

    no_match = map_event_to_topic(
        event_id=104,
        tags=[],
        relations=[],
        latest_extraction_payload={"topic": "macro", "keywords": ["rates", "inflation"]},
    )
    assert no_match.topic is None
    assert no_match.diagnostics.source_layer == "no_match"


def test_novelty_heuristic_uses_prior_equivalent_window_fingerprints():
    now = datetime.utcnow().replace(microsecond=0)
    current = [
        {"id": 1, "mapped_topic": "natural_gas", "impact_score": 80.0, "event_time": now - timedelta(hours=2), "last_updated_at": now - timedelta(hours=2), "event_identity_fingerprint_v2": "id-a", "claim_hash": "claim-a", "latest_extraction_payload": {}, "tags": [], "relations": []},
        {"id": 2, "mapped_topic": "natural_gas", "impact_score": 78.0, "event_time": now - timedelta(hours=1), "last_updated_at": now - timedelta(hours=1), "event_identity_fingerprint_v2": "id-b", "claim_hash": "claim-b", "latest_extraction_payload": {}, "tags": [], "relations": []},
    ]
    prior_overlap = [
        {"id": 10, "mapped_topic": "natural_gas", "impact_score": 60.0, "event_time": now - timedelta(days=1, hours=2), "last_updated_at": now - timedelta(days=1, hours=2), "event_identity_fingerprint_v2": "id-a", "claim_hash": "prior-a", "latest_extraction_payload": {}, "tags": [], "relations": []},
        {"id": 11, "mapped_topic": "natural_gas", "impact_score": 58.0, "event_time": now - timedelta(days=1, hours=1), "last_updated_at": now - timedelta(days=1, hours=1), "event_identity_fingerprint_v2": "id-b", "claim_hash": "prior-b", "latest_extraction_payload": {}, "tags": [], "relations": []},
    ]
    prior_non_overlap = [
        {"id": 20, "mapped_topic": "natural_gas", "impact_score": 60.0, "event_time": now - timedelta(days=1, hours=2), "last_updated_at": now - timedelta(days=1, hours=2), "event_identity_fingerprint_v2": "id-x", "claim_hash": "prior-x", "latest_extraction_payload": {}, "tags": [], "relations": []}
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
    assert ranked_overlap[0].novelty < ranked_non_overlap[0].novelty


def test_external_evidence_normalization_contract_shape():
    payload = {
        "sources": [
            {"source_id": "src_custom", "source_type": "web", "title": "Market Context", "publisher": "Example Publisher", "query": "", "summary": "Gas context confirms tightening constraints.", "claim_support_tags": ["confirmation"], "url": "https://example.com/context"},
            {"source_id": "src_drop", "source_type": "web", "title": "Empty Summary", "publisher": "Example Publisher", "query": "query 2", "summary": "", "claim_support_tags": [], "url": "https://example.com/empty"},
        ]
    }
    now = datetime.utcnow().replace(microsecond=0)
    normalized = _normalize_sources(
        raw_text=json.dumps(payload),
        retrieved_at=now,
        fallback_queries=["fallback_query_1", "fallback_query_2"],
    )
    assert len(normalized) == 1
    assert normalized[0].query == "fallback_query_1"


def test_writer_payload_coercion_supports_section_wrapped_format():
    payload = {
        "title": "Gas Memo",
        "core_thesis_one_liner": {"text": "Gas spread upside repricing is actionable now.", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
        "opportunity_target": {"text": "TTF front-month vs deferred spread.", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
        "market_setup": {"text": "Storage fell while outages persisted.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        "background": {"text": "Event cluster indicated persistent friction.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        "primary_driver": {"text": "Supply disruption remains dominant.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        "supporting_developments": [
            {"text": "Terminal curtailment persisted.", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
            {"text": "Curve steepening accelerated.", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
        ],
        "why_now": {"text": "Window density rose sharply this week.", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
        "why_this_is_an_opportunity": {"text": "Risk premium repricing remains underappreciated.", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
        "trade_expression": {"text": "Express via gas spread futures and options.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        "quantified_evidence_points": [
            {"text": "Storage fell 3.4% WoW.", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
            {"text": "Outage affected 6.2 mtpa.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        ],
        "risks": [
            {"text": "Restart could compress spreads.", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
            {"text": "Policy cap may dampen transmission.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        ],
        "invalidation_triggers": [
            {"text": "Restart confirmed early.", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
            {"text": "Spread compresses two sessions.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        ],
        "watchpoints": [
            {"text": "Terminal timeline updates.", "internal_event_ids": [1], "external_source_ids": ["src_01"]},
            {"text": "Storage and spread path.", "internal_event_ids": [1], "external_source_ids": ["src_02"]},
        ],
        "confidence_level": "medium",
        "conclusion": {"text": "Setup remains actionable with discipline.", "internal_event_ids": [1], "external_source_ids": ["src_03"]},
    }
    coerced = _coerce_writer_payload(payload)
    assert coerced["core_thesis_one_liner"].startswith("Gas spread upside")
    assert len(coerced["quantified_evidence_points"]) == 2


def test_writer_payload_coercion_supports_legacy_alias_keys():
    payload = {
        "memo": {
            "memo_title": "Alias Memo",
            "thesis": "Gas spread repricing is actionable because storage fell in-window.",
            "target_exposure": "TTF basis spread structures.",
            "setup_context": "Supply disruptions and storage draws stacked in the same week.",
            "context": "Clustered events increased balancing stress.",
            "driver": "supply_disruption",
            "supporting_points": ["Flows tightened across key routes.", "Prompt spreads widened."],
            "timing_rationale": "Recent window data accelerated with numeric confirmation.",
            "why_opportunity": "Risk premium transmission appears underappreciated.",
            "positioning": "Use futures spread structures with options overlays.",
            "key_numbers": ["Storage fell 3.4%.", "Outage impacted 6.2 mtpa."],
            "risk_factors": ["Restart risk can compress spreads.", "Policy cap can mute pass-through."],
            "thesis_breakers": ["Early restart confirmation.", "Two-session spread compression."],
            "monitoring_points": ["Terminal restart feeds.", "Storage trajectory updates."],
            "confidence": "High",
            "closing": "Setup remains tradable with invalidation discipline.",
        }
    }
    coerced = _coerce_writer_payload(payload)
    assert coerced["title"] == "Alias Memo"
    assert coerced["market_setup"].startswith("Supply disruptions")
    assert coerced["trade_expression"].startswith("Use futures")
    assert coerced["confidence_level"] == "high"


def test_writer_payload_coercion_supports_sections_array_shape():
    payload = {
        "opportunity_memo": {
            "sections": [
                {"name": "title", "text": "Shipping Repricing Memo"},
                {"name": "core_thesis_one_liner", "text": "Freight repricing is actionable because route frictions tightened rapidly."},
                {"name": "opportunity_target", "text": "Atlantic LNG freight corridor spread exposure."},
                {"name": "market_setup", "text": "Route constraints and delays stacked with freight premium expansion."},
                {"name": "background", "text": "Windowed event cluster showed persistent logistics stress."},
                {"name": "primary_driver", "text": "trade_flow_repricing"},
                {"name": "supporting_developments", "content": ["Delay index rose.", "Insurance premiums increased."]},
                {"name": "why_now", "text": "Recent week showed acceleration in congestion metrics."},
                {"name": "why_this_is_an_opportunity", "text": "Transmission into freight spreads appears underpriced."},
                {"name": "trade_expression", "text": "Use freight-sensitive spread structures with options overlays."},
                {"name": "quantified_evidence_points", "content": ["Delay index up 12%.", "Freight spread widened 9%."]},
                {"name": "risks", "content": ["Rapid route normalization.", "Policy or insurance reset."]},
                {"name": "invalidation_triggers", "content": ["Two-session spread compression.", "Delay index mean reversion."]},
                {"name": "watchpoints", "content": ["Transit updates.", "Insurance rates."]},
                {"name": "confidence_level", "text": "medium"},
                {"name": "conclusion", "text": "Actionable while congestion persists."},
            ]
        }
    }
    coerced = _coerce_writer_payload(payload)
    assert coerced["title"] == "Shipping Repricing Memo"
    assert coerced["market_setup"].startswith("Route constraints")
    assert len(coerced["quantified_evidence_points"]) == 2


def test_writer_hardening_backfills_traceability_and_strengthens_weak_sections():
    input_pack = _base_input_pack()
    external_pack = _external_pack()
    weak_payload = {
        "title": "Weak memo",
        "core_thesis_one_liner": "Shipping may move.",
        "opportunity_target": "Atlantic LNG freight corridor spread exposure.",
        "market_setup": "Setup exists.",
        "background": "Background context.",
        "primary_driver": "",
        "supporting_developments": ["First development", "Second development"],
        "why_now": "It is relevant.",
        "why_this_is_an_opportunity": "This matters broadly.",
        "trade_expression": "Investors should monitor developments.",
        "quantified_evidence_points": ["This seems meaningful.", "It could matter."],
        "risks": ["Uncertainty remains."],
        "invalidation_triggers": ["General developments."],
        "watchpoints": ["Monitor developments.", "Stay informed."],
        "confidence_level": "medium",
        "conclusion": "Conclusion text.",
        "traceability": {"paragraph_sources": []},
    }
    hardened = _harden_payload_with_deterministic_guards(
        payload=weak_payload,
        input_pack=input_pack,
        external_evidence=external_pack,
    )
    assert "because" in hardened["core_thesis_one_liner"].lower()
    assert "window" in hardened["why_now"].lower()
    assert hardened["primary_driver"].strip()
    assert "futures" in hardened["trade_expression"].lower()
    assert "underprice" in hardened["why_this_is_an_opportunity"].lower()
    assert all("monitor developments" not in row.lower() for row in hardened["watchpoints"])
    assert len(hardened["watchpoints"]) >= 2
    assert len(hardened["quantified_evidence_points"]) >= 2
    assert all(any(ch.isdigit() for ch in row) for row in hardened["quantified_evidence_points"][:2])
    assert len(hardened["risks"]) >= 2
    assert len(hardened["invalidation_triggers"]) >= 2
    keys = {row["paragraph_key"] for row in hardened["traceability"]["paragraph_sources"]}
    assert "core_thesis_one_liner" in keys
    assert "quantified_evidence_points[0]" in keys
    assert "watchpoints[1]" in keys


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
            db.commit()

            ranked = rank_topic_candidates(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic_universe=["natural_gas", "oil", "shipping"],
                limit=3,
                recent_memo_topics=set(),
            )
            assert ranked[0].topic == "natural_gas"
            assert ranked[0].event_count >= 3
    finally:
        engine.dispose()


def test_input_builder_returns_stats_and_fact_candidates():
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
                raw_text="raw noise",
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
                raw_text="raw noise",
                payload_topic="commodities",
                payload_keywords=["lng", "outage", "natural gas"],
                tags=[("commodities", "Natural Gas")],
                relations=[("restricts_export_of", "Qatar", "LNG")],
            )
            db.commit()
            pack, _rows = build_opportunity_memo_input_pack(
                db,
                start_time=now - timedelta(hours=6),
                end_time=now,
                topic="natural_gas",
                topic_score=0.9,
                selection_reason="test",
                topic_breakdown={"normalized_event_count": 1.0},
            )
            assert pack.topic_event_stats["event_count"] == 2
            assert pack.driver_evidence_summary["supporting_event_count"] >= 1
            assert len(pack.supporting_fact_candidates) >= 2
    finally:
        engine.dispose()


def test_validator_enforces_quality_and_traceability_rules():
    memo = _valid_memo()
    input_pack = _base_input_pack()
    external_pack = _external_pack()

    passed = validate_opportunity_memo(
        memo=memo,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=3,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert passed.ok is True

    generic_target = memo.model_copy(update={"opportunity_target": "energy markets"})
    failed_target = validate_opportunity_memo(
        memo=generic_target,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=3,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert any(issue.code == "generic_opportunity_target" for issue in failed_target.errors)

    no_quant = memo.model_copy(update={"quantified_evidence_points": ["This was important."]})
    failed_quant = validate_opportunity_memo(
        memo=no_quant,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=3,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert any(issue.code == "insufficient_quantified_evidence" for issue in failed_quant.errors)

    vague_trade = memo.model_copy(update={"trade_expression": "Investors should monitor developments and diversify."})
    failed_trade = validate_opportunity_memo(
        memo=vague_trade,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=3,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert any(issue.code == "vague_trade_expression" for issue in failed_trade.errors)

    vague_why_now = memo.model_copy(update={"why_now": "This remains relevant over time."})
    failed_why_now = validate_opportunity_memo(
        memo=vague_why_now,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=3,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert any(issue.code == "generic_why_now" for issue in failed_why_now.errors)

    generic_opportunity = memo.model_copy(update={"why_this_is_an_opportunity": "This is important for investors in general."})
    failed_opportunity = validate_opportunity_memo(
        memo=generic_opportunity,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=3,
        min_external_sources=3,
        topic_selection_threshold=0.58,
    )
    assert any(issue.code == "generic_opportunity_framing" for issue in failed_opportunity.errors)


def test_renderer_surfaces_core_thesis_and_quantified_evidence():
    memo = _valid_memo()
    rendered = render_opportunity_memo_telegram_html(
        memo=memo,
        topic="natural_gas",
        window_start_utc=datetime(2026, 3, 15, 0, 0, 0),
        window_end_utc=datetime(2026, 3, 22, 0, 0, 0),
    )
    assert "<b>Core Thesis</b>" in rendered
    assert "<b>Quantified Evidence</b>" in rendered
    assert "<b>Trade Expression</b>" in rendered

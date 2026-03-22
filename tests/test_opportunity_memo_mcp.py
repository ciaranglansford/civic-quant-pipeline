from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Event, EventRelation, EventTag, Extraction, RawMessage
from tools.db_mcp_contracts import TOOL_DEFINITIONS
from tools.db_mcp_service import CivicquantDbMcpService, ServiceError


def _seed_event(db, *, now: datetime):
    raw = RawMessage(
        source_channel_id="seed",
        source_channel_name="seed",
        telegram_message_id="mcp-1",
        message_timestamp_utc=now - timedelta(hours=1),
        raw_text="raw text should be ignored for mapping",
        normalized_text="raw text should be ignored for mapping",
    )
    db.add(raw)
    db.flush()

    payload = {
        "topic": "commodities",
        "summary_1_sentence": "Natural gas disruption is tightening supply.",
        "keywords": ["natural gas", "disruption", "supply"],
        "entities": {"countries": ["Qatar"], "orgs": ["Terminal"], "people": [], "tickers": ["TTF"]},
    }
    extraction = Extraction(
        raw_message_id=raw.id,
        extractor_name="extract-and-score-openai-v1",
        schema_version=1,
        event_time=now - timedelta(hours=1),
        topic="commodities",
        impact_score=81.0,
        confidence=0.9,
        sentiment="negative",
        is_breaking=True,
        breaking_window="1h",
        event_fingerprint="mcp-fp",
        event_identity_fingerprint_v2="mcp-fp",
        payload_json=payload,
        canonical_payload_json=payload,
        metadata_json={"impact_scoring": {"calibrated_score": 81.0}},
        claim_hash="mcp-claim",
    )
    db.add(extraction)
    db.flush()

    event = Event(
        event_fingerprint="mcp-event",
        event_identity_fingerprint_v2="mcp-event",
        topic="commodities",
        summary_1_sentence="Natural gas disruption is tightening supply.",
        impact_score=81.0,
        is_breaking=True,
        breaking_window="1h",
        event_time=now - timedelta(hours=1),
        last_updated_at=now - timedelta(hours=1),
        latest_extraction_id=extraction.id,
        claim_hash="mcp-claim",
    )
    db.add(event)
    db.flush()

    db.add(
        EventTag(
            event_id=event.id,
            tag_type="commodities",
            tag_value="Natural Gas",
            tag_source="observed",
            confidence=0.9,
        )
    )
    db.add(
        EventRelation(
            event_id=event.id,
            subject_type="country",
            subject_value="Qatar",
            relation_type="curtails",
            object_type="commodity",
            object_value="Natural Gas",
            relation_source="observed",
            inference_level=0,
            confidence=0.8,
        )
    )
    db.flush()


def test_mcp_tool_definitions_include_opportunity_memo_read_models():
    tool_names = {tool["name"] for tool in TOOL_DEFINITIONS}
    assert "rank_topic_opportunities" in tool_names
    assert "build_opportunity_memo_input" in tool_names
    assert "get_topic_timeline" in tool_names
    assert "get_topic_driver_pack" in tool_names
    assert "get_previous_memo_context" not in tool_names


def test_mcp_opportunity_tools_return_expected_shapes():
    db_path = "./test_civicquant_opportunity_mcp.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    now = datetime.utcnow().replace(microsecond=0)
    try:
        with SessionLocal() as db:
            _seed_event(db, now=now)
            db.commit()

        service = CivicquantDbMcpService(database_url=f"sqlite+pysqlite:///{db_path}")
        window = {
            "start_time": (now - timedelta(hours=6)).isoformat() + "Z",
            "end_time": now.isoformat() + "Z",
        }

        ranked = service.call_tool(
            "rank_topic_opportunities",
            {
                **window,
                "topic_universe": ["natural_gas", "oil"],
                "limit": 5,
            },
        )
        assert ranked["ok"] is True
        assert isinstance(ranked["topics"], list)
        assert ranked["topics"][0]["topic"] == "natural_gas"

        input_pack = service.call_tool(
            "build_opportunity_memo_input",
            {**window, "topic": "natural_gas"},
        )
        assert input_pack["ok"] is True
        assert input_pack["input_pack"]["topic"] == "natural_gas"
        assert input_pack["input_pack"]["selected_event_ids"]

        timeline = service.call_tool(
            "get_topic_timeline",
            {**window, "topic": "natural_gas", "limit": 50},
        )
        assert timeline["ok"] is True
        assert isinstance(timeline["timeline"], list)
        assert timeline["timeline"][0]["event_id"] >= 1

        driver_pack = service.call_tool(
            "get_topic_driver_pack",
            {**window, "topic": "natural_gas"},
        )
        assert driver_pack["ok"] is True
        assert isinstance(driver_pack["drivers"], list)
        assert driver_pack["selected_primary_driver"] is not None
    finally:
        try:
            service.engine.dispose()  # type: ignore[name-defined]
        except Exception:  # noqa: BLE001
            pass
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_mcp_readonly_sql_guard_still_rejects_mutating_sql():
    service = CivicquantDbMcpService(database_url="sqlite+pysqlite:///./civicquant_dev.db")
    with pytest.raises(ServiceError):
        service.call_tool("run_readonly_sql", {"query": "INSERT INTO events(id) VALUES (1)"})

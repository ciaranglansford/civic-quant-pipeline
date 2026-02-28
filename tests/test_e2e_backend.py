from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect


@pytest.fixture(scope="module")
def client():
    db_path = "./test_civicquant.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    os.environ["PHASE2_EXTRACTION_ENABLED"] = "true"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["PHASE2_ADMIN_TOKEN"] = "secret-admin"

    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import init_db
    from app.main import app

    init_db()
    return TestClient(app)


def _payload(channel_id: str, msg_id: str, text: str) -> dict:
    return {
        "source_channel_id": channel_id,
        "source_channel_name": "feed",
        "telegram_message_id": msg_id,
        "message_timestamp_utc": (dt.datetime.utcnow().isoformat() + "Z"),
        "raw_text": text,
        "raw_entities_if_available": None,
        "forwarded_from_if_available": None,
    }


def test_ingest_creates_rows_and_is_idempotent(client: TestClient):
    r = client.post("/ingest/telegram", json=_payload("c1", "m1", "FED hikes 25bp; USD jumps"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "created"
    assert isinstance(body["raw_message_id"], int)
    assert body["event_id"] is None

    r2 = client.post("/ingest/telegram", json=_payload("c1", "m1", "FED hikes 25bp; USD jumps"))
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "duplicate"
    assert body2["raw_message_id"] == body["raw_message_id"]


def test_phase2_manual_trigger_requires_auth(client: TestClient):
    r = client.post("/admin/process/phase2-extractions")
    assert r.status_code == 401


def test_phase2_processes_message_and_is_idempotent(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m2", "ECB signals policy shift; EUR rises 0.5%"))

    from app.services import extraction_llm_client

    def fake_extract(self, prompt_text: str):
        return extraction_llm_client.LlmResponse(
            extractor_name="extract-and-score-openai-v1",
            used_openai=True,
            model_name="gpt-4o-mini",
            openai_response_id="resp_test_1",
            latency_ms=42,
            retries=0,
            raw_text='{"topic":"central_banks","entities":{"countries":["U.S."],"orgs":[" ECB "],"people":[],"tickers":["eur"]},"affected_countries_first_order":["usa"],"market_stats":[{"label":"move","value":0.5,"unit":"%","context":"EUR"}],"sentiment":"neutral","confidence":0.9,"impact_score":55,"is_breaking":false,"breaking_window":"none","event_time":"2025-01-01T00:00:00","source_claimed":" ECB ","summary_1_sentence":"ECB says policy may shift.","keywords":["ECB","EUR"],"event_fingerprint":"central_banks|2025-01-01|us|ecb|||eur|policy_shift"}',
        )

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", fake_extract)

    r = client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})
    assert r.status_code == 200
    out = r.json()
    assert out["selected"] >= 1
    assert out["completed"] >= 1

    r2 = client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})
    assert r2.status_code == 200

    from app.db import SessionLocal
    from app.models import EntityMention, Extraction, MessageProcessingState, RawMessage, RoutingDecision

    with SessionLocal() as db:
        raw = db.query(RawMessage).filter(RawMessage.telegram_message_id == "m2").one()
        extraction_rows = db.query(Extraction).filter(Extraction.raw_message_id == raw.id).all()
        assert len(extraction_rows) == 1
        extraction = extraction_rows[0]
        assert extraction.extractor_name == "extract-and-score-openai-v1"
        assert extraction.schema_version == 1
        assert extraction.topic == "central_banks"
        assert extraction.impact_score == 55
        assert extraction.confidence == 0.9
        assert extraction.sentiment == "neutral"
        assert extraction.event_fingerprint == "central_banks|2025-01-01|United States|ecb|||eur|policy_shift"
        assert extraction.payload_json["topic"] == "central_banks"
        assert extraction.payload_json["entities"]["countries"] == ["U.S."]
        assert extraction.canonical_payload_json is not None
        assert extraction.canonical_payload_json["entities"]["countries"] == ["United States"]
        assert extraction.canonical_payload_json["affected_countries_first_order"] == ["United States"]
        assert extraction.prompt_version == "extraction_agent_v2"
        assert extraction.metadata_json["used_openai"] is True
        assert extraction.metadata_json["openai_model"] == "gpt-4o-mini"
        assert extraction.metadata_json["openai_response_id"] == "resp_test_1"
        assert extraction.metadata_json["latency_ms"] == 42
        assert extraction.metadata_json["canonicalization_rules"]
        decision = db.query(RoutingDecision).filter_by(raw_message_id=raw.id).one()
        assert decision.triage_action in {"monitor", "update", "promote", "archive"}
        assert isinstance(decision.triage_rules, list)
        mentions = db.query(EntityMention).filter(EntityMention.raw_message_id == raw.id).all()
        assert mentions
        assert any(m.entity_type == "country" and m.entity_value == "United States" for m in mentions)
        states = db.query(MessageProcessingState).all()
        assert any(s.status == "completed" for s in states)


def test_phase2_validation_failure_marks_state_failed(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m3", "random text"))

    from app.services import extraction_llm_client

    def bad_extract(self, prompt_text: str):
        return extraction_llm_client.LlmResponse(
            extractor_name="extract-and-score-openai-v1",
            used_openai=True,
            model_name="gpt-4o-mini",
            openai_response_id="resp_test_2",
            latency_ms=7,
            retries=0,
            raw_text='{"bad":"shape"}',
        )

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", bad_extract)

    client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})

    from app.db import SessionLocal
    from app.models import MessageProcessingState

    with SessionLocal() as db:
        failed = db.query(MessageProcessingState).filter(MessageProcessingState.status == "failed").all()
        assert failed
        assert "validation_error" in (failed[-1].last_error or "")


def test_phase2_disabled_raises_error(client: TestClient):
    from app.config import Settings
    from app.db import SessionLocal
    from app.services.phase2_processing import process_phase2_batch

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="PHASE2_EXTRACTION_ENABLED must be true"):
            process_phase2_batch(
                db=db,
                settings=Settings(
                    phase2_extraction_enabled=False,
                    openai_api_key="test-key",
                    database_url=os.environ["DATABASE_URL"],
                ),
            )


def test_extractions_indexes_exist(client: TestClient):
    from app.db import engine

    index_names = {idx["name"] for idx in inspect(engine).get_indexes("extractions")}
    assert "idx_extractions_topic_event_time" in index_names
    assert "idx_extractions_topic_event_time_impact" in index_names

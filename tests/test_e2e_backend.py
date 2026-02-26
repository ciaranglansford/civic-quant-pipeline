from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient


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
            model_name="gpt-4o-mini",
            raw_text='{"topic":"central_banks","entities":{"countries":["EU"],"orgs":["ECB"],"people":[],"tickers":["EUR"]},"affected_countries_first_order":["EU"],"market_stats":[{"label":"move","value":0.5,"unit":"%","context":"EUR"}],"sentiment":"neutral","confidence":0.9,"impact_score":55,"is_breaking":false,"breaking_window":"none","event_time":"2025-01-01T00:00:00","source_claimed":null,"summary_1_sentence":"ECB signals a policy shift.","keywords":["ECB","EUR"],"event_fingerprint":"fingerprint-1"}',
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
    from app.models import Extraction, MessageProcessingState, RawMessage

    with SessionLocal() as db:
        raw = db.query(RawMessage).filter(RawMessage.telegram_message_id == "m2").one()
        assert db.query(Extraction).filter(Extraction.raw_message_id == raw.id).count() == 1
        states = db.query(MessageProcessingState).all()
        assert any(s.status == "completed" for s in states)


def test_phase2_validation_failure_marks_state_failed(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m3", "random text"))

    from app.services import extraction_llm_client

    def bad_extract(self, prompt_text: str):
        return extraction_llm_client.LlmResponse(model_name="gpt-4o-mini", raw_text='{"bad":"shape"}')

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", bad_extract)

    client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})

    from app.db import SessionLocal
    from app.models import MessageProcessingState

    with SessionLocal() as db:
        failed = db.query(MessageProcessingState).filter(MessageProcessingState.status == "failed").all()
        assert failed
        assert "validation_error" in (failed[-1].last_error or "")

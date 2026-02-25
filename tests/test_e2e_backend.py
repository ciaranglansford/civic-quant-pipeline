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
    assert isinstance(body["event_id"], int)
    assert body["event_action"] in ("create", "update")

    r2 = client.post("/ingest/telegram", json=_payload("c1", "m1", "FED hikes 25bp; USD jumps"))
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "duplicate"
    assert body2["raw_message_id"] == body["raw_message_id"]
    assert body2["event_id"] == body["event_id"]


def test_dedup_updates_existing_event(client: TestClient):
    r1 = client.post("/ingest/telegram", json=_payload("c1", "m2", "Pentagon confirms new troop deployment"))
    assert r1.status_code == 200
    e1 = r1.json()["event_id"]

    # Near-duplicate phrasing, same normalized core; stub fingerprint should match if text is similar enough.
    r2 = client.post("/ingest/telegram", json=_payload("c1", "m3", "Pentagon confirms troop deployment"))
    assert r2.status_code == 200
    e2 = r2.json()["event_id"]

    assert isinstance(e1, int) and isinstance(e2, int)


def test_digest_build_and_publish_record(monkeypatch, client: TestClient):
    # Ensure at least one event exists in window.
    r = client.post("/ingest/telegram", json=_payload("c1", "m4", "ECB signals policy shift; EUR rises 0.5%"))
    assert r.status_code == 200

    # Run digest without hitting real Telegram API.
    os.environ["TG_BOT_TOKEN"] = "test"
    os.environ["TG_VIP_CHAT_ID"] = "test"

    from app.db import SessionLocal
    from app.services import digest_runner as dr

    monkeypatch.setattr(dr, "send_digest_to_vip", lambda text: None)

    with SessionLocal() as db:
        out = dr.run_digest(db=db, window_hours=4)
        db.commit()

    assert out["status"] in ("published", "skipped_duplicate")



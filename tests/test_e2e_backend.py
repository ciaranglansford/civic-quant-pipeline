from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="module")
def client():
    os.environ["PHASE2_EXTRACTION_ENABLED"] = "true"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["PHASE2_ADMIN_TOKEN"] = "secret-admin"

    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import Base, get_db
    from app.main import create_app
    import app.db as db_module

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    Base.metadata.create_all(bind=engine)

    original_session_local = db_module.SessionLocal
    db_module.SessionLocal = testing_session_local

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        db_module.SessionLocal = original_session_local
        client.close()
        engine.dispose()


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


def _source_payload(source_type: str, stream_id: str, msg_id: str, text: str) -> dict:
    return {
        "source_type": source_type,
        "source_stream_id": stream_id,
        "source_stream_name": "feed",
        "source_message_id": msg_id,
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


def test_source_ingest_creates_rows_and_is_idempotent(client: TestClient):
    r = client.post(
        "/ingest/source",
        json=_source_payload("telegram", "src-1", "src-msg-1", "BOE hikes 25bp"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "created"
    assert isinstance(body["raw_message_id"], int)

    r2 = client.post(
        "/ingest/source",
        json=_source_payload("telegram", "src-1", "src-msg-1", "BOE hikes 25bp"),
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "duplicate"
    assert body2["raw_message_id"] == body["raw_message_id"]


def test_source_ingest_namespaces_non_telegram_stream_ids(client: TestClient):
    telegram = client.post(
        "/ingest/telegram",
        json=_payload("shared-stream", "shared-msg", "Telegram bulletin"),
    )
    assert telegram.status_code == 200
    assert telegram.json()["status"] == "created"

    source = client.post(
        "/ingest/source",
        json=_source_payload("rss", "shared-stream", "shared-msg", "RSS bulletin"),
    )
    assert source.status_code == 200
    assert source.json()["status"] == "created"

    from app.db import SessionLocal
    from app.models import RawMessage

    with SessionLocal() as db:
        telegram_row = (
            db.query(RawMessage)
            .filter(
                RawMessage.source_channel_id == "shared-stream",
                RawMessage.telegram_message_id == "shared-msg",
            )
            .one()
        )
        source_row = (
            db.query(RawMessage)
            .filter(
                RawMessage.source_channel_id == "rss:shared-stream",
                RawMessage.telegram_message_id == "shared-msg",
            )
            .one()
        )
        assert telegram_row.id != source_row.id


def test_phase2_manual_trigger_requires_auth(client: TestClient):
    r = client.post("/admin/process/phase2-extractions")
    assert r.status_code == 401


def test_phase2_processes_message_and_is_idempotent(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m2", "ECB signals policy shift; EUR rises 0.5%"))

    from app.contexts.extraction import extraction_llm_client

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
        assert extraction.metadata_json["impact_scoring"]["raw_llm_score"] == 55.0
        assert extraction.impact_score == extraction.metadata_json["impact_scoring"]["calibrated_score"]
        assert extraction.confidence == 0.9
        assert extraction.sentiment == "neutral"
        assert extraction.event_fingerprint.startswith("v2:")
        assert len(extraction.event_fingerprint) == 67
        assert extraction.payload_json["topic"] == "central_banks"
        assert extraction.payload_json["entities"]["countries"] == ["U.S."]
        assert extraction.canonical_payload_json is not None
        assert extraction.canonical_payload_json["entities"]["countries"] == ["United States"]
        assert extraction.canonical_payload_json["affected_countries_first_order"] == ["United States"]
        assert extraction.prompt_version == "extraction_agent_v4"
        assert extraction.metadata_json["used_openai"] is True
        assert extraction.metadata_json["openai_model"] == "gpt-4o-mini"
        assert extraction.metadata_json["openai_response_id"] == "resp_test_1"
        assert extraction.metadata_json["latency_ms"] == 42
        assert extraction.metadata_json["canonicalization_rules"]
        assert extraction.metadata_json["backend_event_fingerprint"] == extraction.event_fingerprint
        assert extraction.metadata_json["backend_event_fingerprint_version"] == "v2"
        assert extraction.metadata_json["backend_event_fingerprint_input"].startswith("v2|event_type=")
        assert extraction.metadata_json["llm_event_fingerprint_candidate"] == "central_banks|2025-01-01|us|ecb|||eur|policy_shift"
        assert extraction.metadata_json["impact_scoring"]["score_breakdown"]["score_band_computed_after_rules"] is True
        assert extraction.normalized_text_hash
        assert extraction.replay_identity_key
        assert extraction.canonical_payload_hash
        assert extraction.claim_hash
        assert extraction.event_identity_fingerprint_v2 == extraction.event_fingerprint
        assert extraction.metadata_json["canonicalizer_version"] == "canon_v2"
        assert extraction.metadata_json["canonical_payload_hash"] == extraction.canonical_payload_hash
        assert extraction.metadata_json["claim_hash"] == extraction.claim_hash
        decision = db.query(RoutingDecision).filter_by(raw_message_id=raw.id).one()
        assert decision.triage_action in {"monitor", "update", "promote", "archive"}
        assert isinstance(decision.triage_rules, list)
        mentions = db.query(EntityMention).filter(EntityMention.raw_message_id == raw.id).all()
        assert mentions
        assert any(m.entity_type == "country" and m.entity_value == "United States" for m in mentions)
        states = db.query(MessageProcessingState).all()
        assert any(s.status == "completed" for s in states)


def test_phase2_replay_reuses_existing_extraction_and_skips_model(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m2-replay", "BOE signals policy shift; GBP rises 0.5%"))

    from app.contexts.extraction import extraction_llm_client

    calls = {"count": 0}

    def fake_extract(self, prompt_text: str):
        calls["count"] += 1
        return extraction_llm_client.LlmResponse(
            extractor_name="extract-and-score-openai-v1",
            used_openai=True,
            model_name="gpt-4o-mini",
            openai_response_id=f"resp_replay_{calls['count']}",
            latency_ms=12,
            retries=0,
            raw_text='{"topic":"central_banks","entities":{"countries":["U.S."],"orgs":["ECB"],"people":[],"tickers":["EUR"]},"affected_countries_first_order":["usa"],"market_stats":[{"label":"move","value":0.5,"unit":"%","context":"EUR"}],"sentiment":"neutral","confidence":0.9,"impact_score":55,"is_breaking":false,"breaking_window":"none","event_time":"2025-01-01T00:00:00","source_claimed":"ECB","summary_1_sentence":"ECB says policy may shift.","keywords":["ECB","EUR"],"event_fingerprint":"candidate"}',
        )

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", fake_extract)
    r1 = client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})
    assert r1.status_code == 200
    assert calls["count"] == 1

    from app.db import SessionLocal
    from app.models import Extraction, MessageProcessingState, RawMessage

    with SessionLocal() as db:
        raw = db.query(RawMessage).filter(RawMessage.telegram_message_id == "m2-replay").one()
        state = db.query(MessageProcessingState).filter_by(raw_message_id=raw.id).one()
        state.status = "pending"
        state.lease_expires_at = None
        db.commit()

    r2 = client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})
    assert r2.status_code == 200
    assert calls["count"] == 1

    with SessionLocal() as db:
        raw = db.query(RawMessage).filter(RawMessage.telegram_message_id == "m2-replay").one()
        extraction = db.query(Extraction).filter_by(raw_message_id=raw.id).one()
        assert extraction.metadata_json["replay_reused"] is True
        assert extraction.metadata_json["canonical_payload_unchanged"] is False


def test_phase2_force_reprocess_runs_model_but_keeps_stable_fields_on_same_payload(monkeypatch, client: TestClient):
    from app.contexts.extraction import extraction_llm_client

    calls = {"count": 0}

    def fake_extract(self, prompt_text: str):
        calls["count"] += 1
        return extraction_llm_client.LlmResponse(
            extractor_name="extract-and-score-openai-v1",
            used_openai=True,
            model_name="gpt-4o-mini",
            openai_response_id=f"resp_force_{calls['count']}",
            latency_ms=13,
            retries=0,
            raw_text='{"topic":"central_banks","entities":{"countries":["U.S."],"orgs":["ECB"],"people":[],"tickers":["EUR"]},"affected_countries_first_order":["usa"],"market_stats":[{"label":"move","value":0.5,"unit":"%","context":"EUR"}],"sentiment":"neutral","confidence":0.9,"impact_score":55,"is_breaking":false,"breaking_window":"none","event_time":"2025-01-01T00:00:00","source_claimed":"ECB","summary_1_sentence":"ECB says policy may shift.","keywords":["ECB","EUR"],"event_fingerprint":"candidate"}',
        )

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", fake_extract)

    from app.db import SessionLocal
    from app.models import Extraction, MessageProcessingState, RawMessage

    with SessionLocal() as db:
        raw = db.query(RawMessage).filter(RawMessage.telegram_message_id == "m2-replay").one()
        extraction_before = db.query(Extraction).filter_by(raw_message_id=raw.id).one()
        old_hash = extraction_before.canonical_payload_hash
        old_impact = extraction_before.impact_score
        state = db.query(MessageProcessingState).filter_by(raw_message_id=raw.id).one()
        state.status = "pending"
        state.lease_expires_at = None
        db.commit()

    r = client.post("/admin/process/phase2-extractions?force_reprocess=true", headers={"x-admin-token": "secret-admin"})
    assert r.status_code == 200
    assert calls["count"] >= 1

    with SessionLocal() as db:
        raw = db.query(RawMessage).filter(RawMessage.telegram_message_id == "m2-replay").one()
        extraction_after = db.query(Extraction).filter_by(raw_message_id=raw.id).one()
        assert extraction_after.canonical_payload_hash == old_hash
        assert extraction_after.impact_score == old_impact
        assert extraction_after.metadata_json["canonical_payload_unchanged"] is True


def test_phase2_validation_failure_marks_state_failed(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m3", "random text"))

    from app.contexts.extraction import extraction_llm_client

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


def test_phase2_local_incident_is_downgraded_and_raw_payload_preserved(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m4", "AUSTIN, TX: POLICE REPORT MULTIPLE INJURIES"))

    from app.contexts.extraction import extraction_llm_client

    def extract_local_incident(self, prompt_text: str):
        return extraction_llm_client.LlmResponse(
            extractor_name="extract-and-score-openai-v1",
            used_openai=True,
            model_name="gpt-4o-mini",
            openai_response_id="resp_test_4",
            latency_ms=8,
            retries=0,
            raw_text='{"topic":"war_security","entities":{"countries":["United States"],"orgs":["Austin Police"],"people":[],"tickers":[]},"affected_countries_first_order":["United States"],"market_stats":[],"sentiment":"negative","confidence":0.9,"impact_score":90,"is_breaking":true,"breaking_window":"15m","event_time":"2025-01-01T00:00:00","source_claimed":"Austin Police","summary_1_sentence":"Multiple people injured in Austin, TX incident.","keywords":["police","incident","injured"],"event_fingerprint":"war_security|2025-01-01|United States|austin police|||incident"}',
        )

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", extract_local_incident)
    r = client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})
    assert r.status_code == 200

    from app.db import SessionLocal
    from app.models import Extraction, RawMessage, RoutingDecision

    with SessionLocal() as db:
        raw = db.query(RawMessage).filter(RawMessage.telegram_message_id == "m4").one()
        extraction = db.query(Extraction).filter_by(raw_message_id=raw.id).one()
        decision = db.query(RoutingDecision).filter_by(raw_message_id=raw.id).one()
        assert extraction.payload_json["summary_1_sentence"] == "Multiple people injured in Austin, TX incident."
        assert extraction.canonical_payload_json["summary_1_sentence"] != ""
        assert extraction.metadata_json["impact_scoring"]["raw_llm_score"] == 90.0
        assert extraction.impact_score <= 40.0
        assert decision.triage_action == "monitor"
        assert decision.requires_evidence is True
        assert decision.publish_priority in {"low", "none"}
        assert "triage:local_incident_downgrade" in (decision.triage_rules or [])


def test_phase2_burst_downgrades_same_source_keyword_overlap(monkeypatch, client: TestClient):
    client.post("/ingest/telegram", json=_payload("c1", "m5", "RUSSIAN FOREIGN MINISTRY ON HORMUZ NAVIGATION AND OIL/GAS"))
    client.post("/ingest/telegram", json=_payload("c1", "m6", "RUSSIAN FM: HORMUZ STOPPAGE MAY IMBALANCE OIL AND GAS"))
    client.post("/ingest/telegram", json=_payload("c1", "m7", "RUSSIAN FM SAYS HORMUZ NAVIGATION IMPACTS OIL GAS MARKETS"))

    from app.contexts.extraction import extraction_llm_client

    payloads = [
        '{"topic":"commodities","entities":{"countries":["Russia"],"orgs":[],"people":[],"tickers":[]},"affected_countries_first_order":["Russia"],"market_stats":[],"sentiment":"negative","confidence":0.8,"impact_score":75,"is_breaking":true,"breaking_window":"15m","event_time":"2025-01-01T00:00:00","source_claimed":"Market News Feed","summary_1_sentence":"Russian Foreign Ministry warns Hormuz navigation stoppage may imbalance oil and gas markets.","keywords":["Strait of Hormuz","oil","gas","Russia"],"event_fingerprint":"RUSSIAN_FOREIGN_MINISTRY_STRAIT_OF_HORMUZ_IMPACT"}',
        '{"topic":"commodities","entities":{"countries":["Russia"],"orgs":["Russian Foreign Ministry"],"people":[],"tickers":[]},"affected_countries_first_order":["Russia"],"market_stats":[],"sentiment":"negative","confidence":0.8,"impact_score":75,"is_breaking":true,"breaking_window":"15m","event_time":"2025-01-01T00:00:01","source_claimed":"Market News Feed","summary_1_sentence":"The Russian Foreign Ministry claims stoppage of navigation via Hormuz may imbalance global oil and gas markets.","keywords":["Strait of Hormuz","oil","gas","navigation"],"event_fingerprint":"f2"}',
        '{"topic":"commodities","entities":{"countries":["Russia"],"orgs":["Russian Foreign Ministry"],"people":[],"tickers":[]},"affected_countries_first_order":["Russia"],"market_stats":[],"sentiment":"negative","confidence":0.8,"impact_score":75,"is_breaking":true,"breaking_window":"15m","event_time":"2025-01-01T00:00:02","source_claimed":"Market News Feed","summary_1_sentence":"Russian Foreign Ministry says Hormuz navigation disruption may create oil and gas imbalances.","keywords":["Strait of Hormuz","oil","gas","navigation"],"event_fingerprint":"f3"}',
    ]
    idx = {"value": 0}

    def extract_seq(self, prompt_text: str):
        i = idx["value"]
        idx["value"] += 1
        return extraction_llm_client.LlmResponse(
            extractor_name="extract-and-score-openai-v1",
            used_openai=True,
            model_name="gpt-4o-mini",
            openai_response_id=f"resp_burst_{i}",
            latency_ms=9,
            retries=0,
            raw_text=payloads[i],
        )

    monkeypatch.setattr(extraction_llm_client.OpenAiExtractionClient, "extract", extract_seq)
    r = client.post("/admin/process/phase2-extractions", headers={"x-admin-token": "secret-admin"})
    assert r.status_code == 200

    from app.db import SessionLocal
    from app.models import RawMessage, RoutingDecision

    with SessionLocal() as db:
        ids = [
            db.query(RawMessage).filter(RawMessage.telegram_message_id == mid).one().id
            for mid in ("m5", "m6", "m7")
        ]
        decisions = [db.query(RoutingDecision).filter_by(raw_message_id=rid).one() for rid in ids]
        assert decisions[0].triage_action != "archive"
        assert decisions[1].triage_action in {"monitor", "update", "promote"}
        assert decisions[2].triage_action == "monitor"
        assert "triage:burst_cap_monitor" in (decisions[2].triage_rules or [])


def test_phase2_disabled_raises_error(client: TestClient):
    from app.config import Settings
    from app.db import SessionLocal
    from app.workflows.phase2_pipeline import process_phase2_batch

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
    from app.db import SessionLocal

    with SessionLocal() as db:
        bind = db.get_bind()
        index_names = {idx["name"] for idx in inspect(bind).get_indexes("extractions")}
        assert "idx_extractions_topic_event_time" in index_names
        assert "idx_extractions_topic_event_time_impact" in index_names
        assert "idx_extractions_content_reuse_lookup" in index_names

        table_names = set(inspect(bind).get_table_names())
        assert "enrichment_candidates" in table_names











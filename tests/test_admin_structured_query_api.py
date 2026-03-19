from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.events.structured_persistence import sync_event_tags_and_relations
from app.schemas import ExtractionEntities, ExtractionJson


@pytest.fixture
def client_and_session():
    os.environ["PHASE2_ADMIN_TOKEN"] = "secret-admin"
    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import Base, get_db
    from app.main import create_app
    from app.models import Event

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        yield client, SessionLocal, Event
    finally:
        app.dependency_overrides.clear()
        client.close()
        engine.dispose()


def _seed_extraction(*, country: str, event_time: dt.datetime, directionality: str) -> ExtractionJson:
    return ExtractionJson(
        topic="commodities",
        event_type="production",
        directionality=directionality,
        entities=ExtractionEntities(countries=[country], orgs=["NIOC"], people=[], tickers=[]),
        affected_countries_first_order=[country],
        market_stats=[],
        tags=[
            {"tag_type": "countries", "tag_value": country, "tag_source": "observed", "confidence": 0.9},
            {"tag_type": "commodities", "tag_value": "Oil", "tag_source": "observed", "confidence": 0.9},
            {"tag_type": "directionality", "tag_value": directionality, "tag_source": "observed", "confidence": 0.9},
        ],
        relations=[
            {
                "subject_type": "country",
                "subject_value": country,
                "relation_type": "restricts_export_of",
                "object_type": "commodity",
                "object_value": "Oil",
                "relation_source": "observed",
                "inference_level": 0,
                "confidence": 0.8,
            }
        ],
        impact_inputs={},
        sentiment="negative",
        confidence=0.8,
        impact_score=75.0,
        is_breaking=True,
        breaking_window="1h",
        event_time=event_time,
        source_claimed="Reuters",
        summary_1_sentence=f"{country} restricts oil exports.",
        keywords=["oil"],
        event_core="restriction",
        event_fingerprint=f"seed-{country}",
    )


def test_admin_structured_query_requires_auth(client_and_session):
    client, _, _ = client_and_session
    response = client.get(
        "/admin/query/events/by-tag",
        params={
            "tag_type": "commodities",
            "tag_value": "Oil",
            "start_time": dt.datetime.utcnow().isoformat(),
            "end_time": dt.datetime.utcnow().isoformat(),
        },
    )
    assert response.status_code == 401


def test_admin_structured_query_endpoints_delegate_to_helpers(client_and_session):
    client, SessionLocal, Event = client_and_session
    now = dt.datetime.utcnow().replace(microsecond=0)

    with SessionLocal() as db:
        event = Event(
            event_fingerprint="admin-query-event",
            topic="commodities",
            summary_1_sentence="Iran restricts oil exports.",
            impact_score=82.0,
            is_breaking=True,
            breaking_window="1h",
            event_time=now - dt.timedelta(hours=1),
            last_updated_at=now - dt.timedelta(hours=1),
        )
        db.add(event)
        db.flush()
        sync_event_tags_and_relations(
            db,
            event_id=event.id,
            extraction=_seed_extraction(country="Iran", event_time=event.event_time, directionality="stress"),
        )
        db.commit()

    params = {
        "tag_type": "commodities",
        "tag_value": "Oil",
        "start_time": (now - dt.timedelta(hours=6)).isoformat(),
        "end_time": now.isoformat(),
        "min_impact": 70,
        "directionality": "stress",
    }
    by_tag = client.get("/admin/query/events/by-tag", params=params, headers={"x-admin-token": "secret-admin"})
    assert by_tag.status_code == 200
    payload = by_tag.json()
    assert payload["count"] == 1
    assert payload["items"][0]["summary"] == "Iran restricts oil exports."

    by_relation = client.get(
        "/admin/query/events/by-relation",
        params={
            "relation_type": "restricts_export_of",
            "start_time": (now - dt.timedelta(hours=6)).isoformat(),
            "end_time": now.isoformat(),
            "directionality": "stress",
        },
        headers={"x-admin-token": "secret-admin"},
    )
    assert by_relation.status_code == 200
    rel_payload = by_relation.json()
    assert rel_payload["count"] == 1
    assert rel_payload["items"][0]["id"] == payload["items"][0]["id"]

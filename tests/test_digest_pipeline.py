from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.digest.adapters.base import PublishResult
from app.digest.builder import build_canonical_digest
from app.digest.orchestrator import run_digest
from app.digest.query import get_events_for_window
from app.digest.renderer_text import render_canonical_text
from app.digest.types import DigestWindow
from app.models import DigestArtifact, Event, PublishedPost


def _session_factory(db_path: str):
    if os.path.exists(db_path):
        os.remove(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal, engine


def _seed_event(
    db,
    *,
    fingerprint: str,
    topic: str | None,
    summary: str,
    impact: float | None,
    updated_at: datetime,
) -> Event:
    row = Event(
        event_fingerprint=fingerprint,
        topic=topic,
        summary_1_sentence=summary,
        impact_score=impact,
        event_time=updated_at,
        last_updated_at=updated_at,
    )
    db.add(row)
    db.flush()
    return row


def test_digest_query_selection_window_boundaries_and_ordering():
    db_path = "./test_civicquant_digest_query.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            start = datetime(2026, 1, 1, 0, 0, 0)
            end = datetime(2026, 1, 1, 4, 0, 0)

            excluded_before = _seed_event(
                db,
                fingerprint="e-before",
                topic="fx",
                summary="before",
                impact=10.0,
                updated_at=start - timedelta(seconds=1),
            )
            included_start = _seed_event(
                db,
                fingerprint="e-start",
                topic="fx",
                summary="start",
                impact=20.0,
                updated_at=start,
            )
            included_later = _seed_event(
                db,
                fingerprint="e-later",
                topic="fx",
                summary="later",
                impact=30.0,
                updated_at=start + timedelta(hours=1),
            )
            tie_1 = _seed_event(
                db,
                fingerprint="e-tie-1",
                topic="fx",
                summary="tie1",
                impact=40.0,
                updated_at=start + timedelta(hours=1),
            )
            tie_2 = _seed_event(
                db,
                fingerprint="e-tie-2",
                topic="fx",
                summary="tie2",
                impact=50.0,
                updated_at=start + timedelta(hours=1),
            )
            excluded_end = _seed_event(
                db,
                fingerprint="e-end",
                topic="fx",
                summary="end",
                impact=60.0,
                updated_at=end,
            )
            db.commit()

            selected = get_events_for_window(db, window_start_utc=start, window_end_utc=end)
            selected_ids = [row.id for row in selected]

            assert excluded_before.id not in selected_ids
            assert excluded_end.id not in selected_ids
            assert included_start.id in selected_ids
            assert included_later.id in selected_ids
            assert tie_1.id in selected_ids
            assert tie_2.id in selected_ids

            # last_updated_at desc, then event id asc for ties
            tied_ids_sorted = sorted([included_later.id, tie_1.id, tie_2.id])
            tied_ids_actual = [row.id for row in selected if row.last_updated_at == tie_1.last_updated_at]
            assert tied_ids_actual == tied_ids_sorted
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_canonical_builder_groups_topics_and_sorts_deterministically():
    db_path = "./test_civicquant_digest_builder.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 1, 0, 0, 0)
            e1 = _seed_event(
                db,
                fingerprint="b1",
                topic="fx",
                summary="FX item",
                impact=11.0,
                updated_at=now + timedelta(minutes=2),
            )
            e2 = _seed_event(
                db,
                fingerprint="b2",
                topic="central_banks",
                summary="CB item newer",
                impact=22.0,
                updated_at=now + timedelta(minutes=4),
            )
            e3 = _seed_event(
                db,
                fingerprint="b3",
                topic="central_banks",
                summary="CB item older",
                impact=33.0,
                updated_at=now + timedelta(minutes=1),
            )
            db.commit()

            window = DigestWindow(
                start_utc=now,
                end_utc=now + timedelta(hours=4),
                hours=4,
            )
            digest = build_canonical_digest([e1, e2, e3], window=window)

            labels = [section.topic_label for section in digest.sections]
            assert labels == ["Central Banks", "FX"]

            cb_section = digest.sections[0]
            assert [item.event_id for item in cb_section.items] == [e2.id, e3.id]
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_renderer_is_byte_stable_for_identical_canonical_digest():
    db_path = "./test_civicquant_digest_renderer.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 1, 0, 0, 0)
            e1 = _seed_event(
                db,
                fingerprint="r1",
                topic="fx",
                summary="Renderer item",
                impact=15.5,
                updated_at=now + timedelta(minutes=3),
            )
            db.commit()

            window = DigestWindow(
                start_utc=now,
                end_utc=now + timedelta(hours=4),
                hours=4,
            )
            digest = build_canonical_digest([e1], window=window)
            text_a = render_canonical_text(digest)
            text_b = render_canonical_text(digest)

            assert text_a == text_b
            assert "generated" not in text_a.lower()
            assert text_a.startswith("Window 2026-01-01 00:00:00 UTC to 2026-01-01 04:00:00 UTC")
            assert "2026-01-01 00:00:00 UTC" in text_a
            assert "impact=" not in text_a
            assert "corroboration=" not in text_a
            assert "informational only" not in text_a.lower()
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_orchestrator_persists_artifact_before_publish_attempt():
    db_path = "./test_civicquant_digest_artifact_first.db"
    SessionLocal, engine = _session_factory(db_path)

    class ProbeAdapter:
        destination = "probe_destination"

        def __init__(self, session_factory):
            self.session_factory = session_factory

        def render_payload(self, digest, canonical_text):  # noqa: ANN001
            return canonical_text

        def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
            with self.session_factory() as verify_db:
                # This should succeed only if artifact commit happened before publish.
                assert verify_db.query(DigestArtifact).count() >= 1
            return PublishResult(status="published", external_ref="probe-ok")

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 2, 0, 0, 0)
            _seed_event(
                db,
                fingerprint="a1",
                topic="fx",
                summary="Artifact first",
                impact=40.0,
                updated_at=now - timedelta(minutes=5),
            )
            db.commit()

            out = run_digest(
                db,
                window_hours=4,
                now_utc=now,
                adapters=[ProbeAdapter(SessionLocal)],
            )
            assert out["status"] == "completed"

            artifact_count = db.query(DigestArtifact).count()
            assert artifact_count == 1
            posts = db.query(PublishedPost).all()
            assert len(posts) == 1
            assert posts[0].status == "published"
            assert posts[0].artifact_id is not None
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_rerun_skips_successful_destination():
    db_path = "./test_civicquant_digest_rerun_skip.db"
    SessionLocal, engine = _session_factory(db_path)

    class CountingAdapter:
        destination = "counting_destination"

        def __init__(self):
            self.publish_calls = 0

        def render_payload(self, digest, canonical_text):  # noqa: ANN001
            return canonical_text

        def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
            self.publish_calls += 1
            return PublishResult(status="published", external_ref="counting-ok")

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 3, 0, 0, 0)
            _seed_event(
                db,
                fingerprint="s1",
                topic="fx",
                summary="Skip on rerun",
                impact=40.0,
                updated_at=now - timedelta(minutes=10),
            )
            db.commit()

            adapter = CountingAdapter()
            run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])
            run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])

            assert adapter.publish_calls == 1
            row = db.query(PublishedPost).one()
            assert row.status == "published"
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_rerun_retries_failed_destination():
    db_path = "./test_civicquant_digest_rerun_retry.db"
    SessionLocal, engine = _session_factory(db_path)

    class FlakyAdapter:
        destination = "flaky_destination"

        def __init__(self):
            self.publish_calls = 0

        def render_payload(self, digest, canonical_text):  # noqa: ANN001
            return canonical_text

        def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
            self.publish_calls += 1
            if self.publish_calls == 1:
                raise RuntimeError("first publish attempt fails")
            return PublishResult(status="published", external_ref="flaky-ok")

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 4, 0, 0, 0)
            _seed_event(
                db,
                fingerprint="f1",
                topic="fx",
                summary="Retry failed destination",
                impact=40.0,
                updated_at=now - timedelta(minutes=10),
            )
            db.commit()

            adapter = FlakyAdapter()
            run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])
            row_after_fail = db.query(PublishedPost).one()
            assert row_after_fail.status == "failed"

            run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])
            row_after_retry = db.query(PublishedPost).one()
            assert row_after_retry.status == "published"
            assert adapter.publish_calls == 2
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_orchestrator_filters_out_events_with_impact_30_or_lower():
    db_path = "./test_civicquant_digest_impact_filter.db"
    SessionLocal, engine = _session_factory(db_path)

    class CountingAdapter:
        destination = "counting_destination"

        def __init__(self):
            self.publish_calls = 0

        def render_payload(self, digest, canonical_text):  # noqa: ANN001
            return canonical_text

        def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
            self.publish_calls += 1
            return PublishResult(status="published", external_ref="ok")

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 5, 0, 0, 0)
            _seed_event(
                db,
                fingerprint="i-low",
                topic="fx",
                summary="Low impact excluded",
                impact=30.0,
                updated_at=now - timedelta(minutes=5),
            )
            _seed_event(
                db,
                fingerprint="i-high",
                topic="fx",
                summary="High impact included",
                impact=31.0,
                updated_at=now - timedelta(minutes=4),
            )
            db.commit()

            adapter = CountingAdapter()
            out = run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])
            assert out["status"] == "completed"
            assert adapter.publish_calls == 1

            artifact = db.query(DigestArtifact).one()
            assert "High impact included" in artifact.canonical_text
            assert "Low impact excluded" not in artifact.canonical_text
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_telegram_publish_marks_event_flag_and_rerun_passes_over():
    db_path = "./test_civicquant_digest_telegram_flag.db"
    SessionLocal, engine = _session_factory(db_path)

    class TelegramLikeAdapter:
        destination = "vip_telegram"

        def __init__(self):
            self.publish_calls = 0

        def render_payload(self, digest, canonical_text):  # noqa: ANN001
            return canonical_text

        def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
            self.publish_calls += 1
            return PublishResult(status="published", external_ref="telegram-msg-1")

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 6, 0, 0, 0)
            event = _seed_event(
                db,
                fingerprint="t1",
                topic="fx",
                summary="Telegram publish once",
                impact=45.0,
                updated_at=now - timedelta(minutes=8),
            )
            db.commit()

            adapter = TelegramLikeAdapter()
            run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])
            db.refresh(event)
            assert event.is_published_telegram is True

            run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])
            assert adapter.publish_calls == 1
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)

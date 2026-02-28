from __future__ import annotations

import os
from datetime import datetime, timedelta


def test_selector_handles_pending_failed_and_expired_in_progress():
    db_path = "./test_civicquant_phase2_services.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"

    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import SessionLocal, init_db
    from app.models import MessageProcessingState, RawMessage
    from app.services.phase2_processing import get_eligible_messages_for_extraction

    init_db()

    with SessionLocal() as db:
        now = datetime.utcnow()
        rows = [
            RawMessage(source_channel_id="b", telegram_message_id="11", message_timestamp_utc=now, raw_text="x", normalized_text="x"),
            RawMessage(source_channel_id="b", telegram_message_id="12", message_timestamp_utc=now + timedelta(seconds=1), raw_text="x", normalized_text="x"),
            RawMessage(source_channel_id="b", telegram_message_id="13", message_timestamp_utc=now + timedelta(seconds=2), raw_text="x", normalized_text="x"),
            RawMessage(source_channel_id="b", telegram_message_id="14", message_timestamp_utc=now + timedelta(seconds=3), raw_text="x", normalized_text="x"),
        ]
        db.add_all(rows)
        db.flush()
        db.add_all(
            [
                MessageProcessingState(raw_message_id=rows[0].id, status="pending", attempt_count=0),
                MessageProcessingState(raw_message_id=rows[1].id, status="failed", attempt_count=1),
                MessageProcessingState(raw_message_id=rows[2].id, status="in_progress", attempt_count=1, lease_expires_at=now - timedelta(seconds=10)),
                MessageProcessingState(raw_message_id=rows[3].id, status="in_progress", attempt_count=1, lease_expires_at=now + timedelta(seconds=600)),
            ]
        )
        db.commit()

        eligible = get_eligible_messages_for_extraction(db, batch_size=10)
        ids = [r.telegram_message_id for r in eligible if r.source_channel_id == "b"]
        assert ids == ["11", "12", "13"]

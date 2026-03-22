from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from sqlalchemy import text

from ..db import SessionLocal, engine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.reset")


TABLES_TO_CLEAR_IN_ORDER = [
    "event_messages",
    "opportunity_memo_deliveries",
    "opportunity_memo_external_sources",
    "opportunity_memo_input_events",
    "opportunity_memo_artifacts",
    "opportunity_memo_runs",
    "thesis_cards",
    "theme_opportunity_assessments",
    "theme_brief_artifacts",
    "event_theme_evidence",
    "theme_runs",
    "published_posts",
    "digest_artifacts",
    "events",
    "routing_decisions",
    "extractions",
    "message_processing_states",
    "processing_locks",
]


def _env_flag_enabled(name: str) -> bool:
    raw = (os.getenv(name) or "").strip().strip('"').strip("'").lower()
    return raw in {"1", "true", "yes", "y", "on"}


def main() -> None:
    load_dotenv()

    if not _env_flag_enabled("CONFIRM_CLEAR_NON_RAW"):
        raise RuntimeError("Set CONFIRM_CLEAR_NON_RAW=true to run this reset script")

    with SessionLocal() as db:
        for table in TABLES_TO_CLEAR_IN_ORDER:
            db.execute(text(f"DELETE FROM {table}"))
            logger.info("cleared table=%s", table)
        db.commit()

    # This makes SQLite tests/dev runs start IDs from 1 again where possible.
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM sqlite_sequence"))

    logger.info("clear complete (raw_messages preserved)")


if __name__ == "__main__":
    main()

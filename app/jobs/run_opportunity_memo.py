from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..workflows.opportunity_memo_pipeline import run_opportunity_memo


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.opportunity_memo")


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one on-demand opportunity memo workflow.")
    parser.add_argument("--start", required=True, help="ISO-8601 UTC start timestamp.")
    parser.add_argument("--end", required=True, help="ISO-8601 UTC end timestamp.")
    parser.add_argument("--topic", required=False, default=None, help="Optional manual topic override.")
    args = parser.parse_args()

    start_time = _parse_iso_datetime(args.start)
    end_time = _parse_iso_datetime(args.end)

    load_dotenv()
    settings = get_settings()
    init_db()

    with SessionLocal() as db:
        result = run_opportunity_memo(
            db,
            start_time=start_time,
            end_time=end_time,
            topic=args.topic,
            settings=settings,
        )
        db.commit()

        logger.info(
            "opportunity_memo_summary run_id=%s status=%s selected_topic=%s topic_score=%s artifact_id=%s delivery_status=%s validation_errors=%s message=%s",
            result.run_id,
            result.status,
            result.selected_topic,
            result.topic_score,
            result.artifact_id,
            result.delivery_status,
            result.validation_errors,
            result.message,
        )


if __name__ == "__main__":
    main()

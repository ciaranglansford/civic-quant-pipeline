from __future__ import annotations

import logging

from dotenv import load_dotenv

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..workflows.deep_enrichment_pipeline import process_deep_enrichment_batch


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.deep_enrichment")


def main() -> None:
    load_dotenv()
    settings = get_settings()
    init_db()

    with SessionLocal() as db:
        summary = process_deep_enrichment_batch(db, settings=settings)
        db.commit()
        logger.info(
            "deep_enrichment_summary run_id=%s selected=%s processed=%s created=%s skipped_existing=%s lock_busy=%s",
            summary.run_id,
            summary.selected,
            summary.processed,
            summary.created,
            summary.skipped_existing,
            summary.lock_busy,
        )


if __name__ == "__main__":
    main()

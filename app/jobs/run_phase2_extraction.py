from __future__ import annotations

import logging

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..services.phase2_processing import process_phase2_batch


logging.basicConfig(level=logging.INFO)


def main() -> None:
    settings = get_settings()
    init_db()
    with SessionLocal() as db:
        summary = process_phase2_batch(db=db, settings=settings)
        db.commit()
        logging.getLogger("civicquant.phase2").info("phase2_job_summary=%s", summary)


if __name__ == "__main__":
    main()

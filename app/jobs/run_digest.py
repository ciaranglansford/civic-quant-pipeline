from __future__ import annotations

import logging

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..services.digest_runner import run_digest


logging.basicConfig(level=logging.INFO)


def main() -> None:
    settings = get_settings()
    init_db()
    with SessionLocal() as db:
        run_digest(db=db, window_hours=settings.vip_digest_hours)
        db.commit()


if __name__ == "__main__":
    main()


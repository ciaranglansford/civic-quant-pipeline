from __future__ import annotations

import logging

from dotenv import load_dotenv
from sqlalchemy import inspect

from ..db import engine, init_db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.opportunity_memo_schema")


EXPECTED_TABLES = (
    "opportunity_memo_runs",
    "opportunity_memo_artifacts",
    "opportunity_memo_input_events",
    "opportunity_memo_external_sources",
    "opportunity_memo_deliveries",
)


def main() -> None:
    load_dotenv()

    init_db()
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = sorted(set(EXPECTED_TABLES) - existing)
    if missing:
        raise RuntimeError(
            f"opportunity memo schema adoption incomplete; missing tables: {','.join(missing)}"
        )
    logger.info("opportunity_memo_schema_adoption_complete tables=%s", ",".join(EXPECTED_TABLES))


if __name__ == "__main__":
    main()

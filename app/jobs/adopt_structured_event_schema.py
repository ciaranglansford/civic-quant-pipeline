from __future__ import annotations

import logging

from dotenv import load_dotenv
from sqlalchemy import inspect, text

from ..db import Base, engine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.structured_schema")


EXPECTED_TABLES = (
    "event_tags",
    "event_relations",
    "event_deep_enrichments",
)


def _ensure_enrichment_route_column() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("enrichment_candidates")}
    if "enrichment_route" in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE enrichment_candidates "
                "ADD COLUMN enrichment_route VARCHAR(32) NOT NULL DEFAULT 'store_only'"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_enrichment_candidates_route_selected_scored "
                "ON enrichment_candidates(enrichment_route, selected, scored_at)"
            )
        )
    logger.info("added enrichment_candidates.enrichment_route")


def main() -> None:
    load_dotenv()

    # Non-destructive adoption of additive structured-event tables/indexes.
    Base.metadata.create_all(bind=engine)
    _ensure_enrichment_route_column()

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = sorted(set(EXPECTED_TABLES) - existing)
    if missing:
        raise RuntimeError(
            f"structured event schema adoption incomplete; missing tables: {','.join(missing)}"
        )
    logger.info("structured_event_schema_adoption_complete tables=%s", ",".join(EXPECTED_TABLES))


if __name__ == "__main__":
    main()

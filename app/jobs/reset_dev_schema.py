from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from ..db import Base, engine
from .. import models  # noqa: F401


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.schema")


def _env_flag_enabled(name: str) -> bool:
    raw = (os.getenv(name) or "").strip().strip('"').strip("'").lower()
    return raw in {"1", "true", "yes", "y", "on"}


def main() -> None:
    load_dotenv()
    # if not _env_flag_enabled("CONFIRM_RESET_DEV_SCHEMA"):
    #     raise RuntimeError("Set CONFIRM_RESET_DEV_SCHEMA=true to reset schema")

    logger.warning("reset_dev_schema starting")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.warning("reset_dev_schema complete")


if __name__ == "__main__":
    main()

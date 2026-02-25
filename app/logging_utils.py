from __future__ import annotations

import logging
import uuid


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level)


def new_request_id() -> str:
    return uuid.uuid4().hex


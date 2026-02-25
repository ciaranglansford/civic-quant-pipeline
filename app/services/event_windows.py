from __future__ import annotations

from datetime import timedelta


def get_event_time_window(topic: str, is_breaking: bool) -> timedelta:
    if topic == "macro_econ":
        return timedelta(hours=48)
    if is_breaking:
        return timedelta(hours=6)
    return timedelta(hours=24)


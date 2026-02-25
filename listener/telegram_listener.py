from __future__ import annotations

import asyncio
import logging
import os
from datetime import timezone

import httpx
from telethon import TelegramClient, events


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.listener")


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def build_ingest_payload(message, source_channel_id: str, source_channel_name: str | None) -> dict:
    dt = message.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)

    forwarded_from = None
    if getattr(message, "fwd_from", None) and getattr(message.fwd_from, "from_name", None):
        forwarded_from = message.fwd_from.from_name

    return {
        "source_channel_id": str(source_channel_id),
        "source_channel_name": source_channel_name,
        "telegram_message_id": str(message.id),
        "message_timestamp_utc": dt_utc.isoformat().replace("+00:00", "Z"),
        "raw_text": message.message or "",
        "raw_entities_if_available": None,
        "forwarded_from_if_available": forwarded_from,
    }


async def post_with_retries(url: str, payload: dict, max_attempts: int = 5) -> None:
    backoff_s = 1.0
    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                r = await client.post(url, json=payload)
                if 200 <= r.status_code < 300:
                    logger.info(
                        "post_ok telegram_message_id=%s attempt=%s status=%s",
                        payload.get("telegram_message_id"),
                        attempt,
                        r.status_code,
                    )
                    return
                if r.status_code == 429 or r.status_code >= 500:
                    logger.warning(
                        "post_retryable telegram_message_id=%s attempt=%s status=%s body=%s",
                        payload.get("telegram_message_id"),
                        attempt,
                        r.status_code,
                        r.text[:300],
                    )
                else:
                    logger.error(
                        "post_nonretryable telegram_message_id=%s attempt=%s status=%s body=%s",
                        payload.get("telegram_message_id"),
                        attempt,
                        r.status_code,
                        r.text[:300],
                    )
                    return
            except Exception as e:
                logger.warning(
                    "post_error telegram_message_id=%s attempt=%s error=%s",
                    payload.get("telegram_message_id"),
                    attempt,
                    type(e).__name__,
                )

            if attempt < max_attempts:
                await asyncio.sleep(backoff_s)
                backoff_s = min(backoff_s * 2.0, 30.0)

    logger.error(
        "post_failed telegram_message_id=%s attempts=%s",
        payload.get("telegram_message_id"),
        max_attempts,
    )


async def main() -> None:
    api_id = int(_require_env("TG_API_ID"))
    api_hash = _require_env("TG_API_HASH")
    session_name = _require_env("TG_SESSION_NAME")
    source_channel = _require_env("TG_SOURCE_CHANNEL")
    ingest_base = _require_env("INGEST_API_BASE_URL").rstrip("/")

    ingest_url = f"{ingest_base}/ingest/telegram"

    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    entity = await client.get_entity(source_channel)
    source_channel_id = getattr(entity, "id", source_channel)
    source_channel_name = getattr(entity, "title", None) or getattr(entity, "username", None)

    logger.info(
        "listener_started source_channel=%s source_channel_id=%s",
        source_channel,
        source_channel_id,
    )

    @client.on(events.NewMessage(chats=entity))
    async def handler(event) -> None:
        msg = event.message
        payload = build_ingest_payload(msg, str(source_channel_id), source_channel_name)
        await post_with_retries(ingest_url, payload)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())


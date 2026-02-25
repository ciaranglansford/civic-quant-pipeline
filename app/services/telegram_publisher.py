from __future__ import annotations

import logging

import httpx

from ..config import get_settings


logger = logging.getLogger("civicquant.publisher.telegram")


def send_digest_to_vip(text: str) -> None:
    settings = get_settings()
    if not settings.tg_bot_token or not settings.tg_vip_chat_id:
        raise RuntimeError("TG_BOT_TOKEN and TG_VIP_CHAT_ID must be configured to publish digests")

    url = f"https://api.telegram.org/bot{settings.tg_bot_token}/sendMessage"
    payload = {"chat_id": settings.tg_vip_chat_id, "text": text, "disable_web_page_preview": True}

    with httpx.Client(timeout=20.0) as client:
        r = client.post(url, json=payload)
        if r.status_code >= 400:
            logger.error("telegram_publish_failed status=%s body=%s", r.status_code, r.text[:500])
            r.raise_for_status()
        logger.info("telegram_publish_ok status=%s", r.status_code)


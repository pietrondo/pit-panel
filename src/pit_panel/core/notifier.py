"""Notification dispatcher — Telegram bot."""

import logging

import httpx

from pit_panel.config import get_settings

logger = logging.getLogger(__name__)


async def send_telegram(message: str) -> bool:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            resp = await client.post(url, json=payload)
            ok = resp.status_code == 200
            if not ok:
                logger.warning("Telegram send failed: %s", resp.text[:200])
            return ok
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


async def notify_app_backup(subdomain: str, name: str, size: str) -> None:
    msg = f"<b>📦 Backup created</b>\nApp: {subdomain}\nFile: {name}.tar.gz\nSize: {size}"
    await send_telegram(msg)


async def notify_app_update(subdomain: str) -> None:
    await send_telegram(f"<b>🔄 App updated</b>\nApp: {subdomain}")


async def notify_test() -> bool:
    return await send_telegram("<b>✅ pit-panel</b>\nTelegram notifications work!")

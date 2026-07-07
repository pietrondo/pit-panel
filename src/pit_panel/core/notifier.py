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


async def notify_app_deploy(subdomain: str, stack: str, fqdn: str) -> None:
    await send_telegram(
        f"<b>🚀 App deployed</b>\nName: {subdomain}\nStack: {stack}\nURL: https://{fqdn}"
    )


async def notify_app_delete(subdomain: str, stack: str) -> None:
    await send_telegram(f"<b>🗑️ App deleted</b>\nName: {subdomain}\nStack: {stack}")


async def notify_login_failed(username: str, ip: str) -> None:
    """Send notification for failed login."""
    msg = f"⚠️ <b>Failed Login Attempt</b>\nUser: <code>{username}</code>\nIP: <code>{ip}</code>"
    await send_telegram(msg)


async def notify_login_success(username: str, ip: str) -> None:
    await send_telegram(f"<b>🔓 Login success</b>\nUser: {username}\nIP: {ip}")


async def notify_ssl_expiring(domains: list[str], days: int) -> None:
    d = ", ".join(domains[:3])
    if len(domains) > 3:
        d += f" (+{len(domains) - 3} more)"
    await send_telegram(f"<b>🔐 SSL cert expiring in {days}d</b>\n{d}")


async def notify_system_alarm(title: str, detail: str) -> None:
    await send_telegram(f"<b>🚨 {title}</b>\n{detail}")


async def notify_test() -> bool:
    return await send_telegram("<b>✅ pit-panel</b>\nTelegram notifications work!")

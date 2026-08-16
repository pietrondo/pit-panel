"""IP ban management and brute-force protection."""

import datetime as dt
import time
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.db.models import IPBan, LoginAttempt

MAX_FAILED_ATTEMPTS = 5
BAN_DURATION_MINUTES = 30
FAILED_WINDOW_MINUTES = 15

_IP_BAN_CACHE: dict[str, tuple[float, bool]] = {}
MAX_CACHE_SIZE = 1000
CACHE_TTL_SECONDS = 30.0


def is_ip_banned_fast(ip: str) -> bool | None:
    now = time.monotonic()
    if ip in _IP_BAN_CACHE:
        cached_at, is_banned = _IP_BAN_CACHE[ip]
        if now - cached_at < CACHE_TTL_SECONDS:
            return is_banned
    return None


async def is_ip_banned(db: AsyncSession, ip: str) -> bool:
    now = time.monotonic()

    if ip in _IP_BAN_CACHE:
        cached_at, is_banned = _IP_BAN_CACHE[ip]
        if now - cached_at < CACHE_TTL_SECONDS:
            return is_banned

    result = await db.execute(
        select(IPBan).where(
            IPBan.ip_address == ip,
            (IPBan.expires_at.is_(None)) | (IPBan.expires_at > dt.datetime.now(dt.UTC)),
        )
    )
    banned = result.scalar_one_or_none() is not None

    if len(_IP_BAN_CACHE) >= MAX_CACHE_SIZE:
        _IP_BAN_CACHE.clear()

    _IP_BAN_CACHE[ip] = (now, banned)
    return banned


async def record_login_attempt(db: AsyncSession, ip: str, username: str, success: bool) -> None:
    # Never ban localhost
    if ip in ("127.0.0.1", "::1", "localhost"):
        return

    attempt = LoginAttempt(ip_address=ip, username=username, success=success)
    db.add(attempt)
    await db.commit()

    if not success:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=FAILED_WINDOW_MINUTES)

        result = await db.execute(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.ip_address == ip,
                LoginAttempt.success == False,  # noqa: E712
                LoginAttempt.attempted_at > cutoff,
            )
        )
        failed_count = result.scalar_one()

        if failed_count >= MAX_FAILED_ATTEMPTS:
            existing = await db.execute(select(IPBan).where(IPBan.ip_address == ip))
            ban = existing.scalar_one_or_none()
            if ban:
                ban.failed_attempts = failed_count
                ban.expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    minutes=BAN_DURATION_MINUTES
                )
            else:
                ban = IPBan(
                    ip_address=ip,
                    reason=f"auto: {failed_count} failed logins in {FAILED_WINDOW_MINUTES}min",
                    failed_attempts=failed_count,
                    expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=BAN_DURATION_MINUTES),
                )
                db.add(ban)
            await db.commit()
            _IP_BAN_CACHE.pop(ip, None)


async def unban_ip(db: AsyncSession, ip: str, user_id: int | None = None) -> bool:
    result = await db.execute(select(IPBan).where(IPBan.ip_address == ip))
    ban = result.scalar_one_or_none()
    if ban:
        await db.delete(ban)
        await db.commit()
        _IP_BAN_CACHE.pop(ip, None)
        return True
    return False


async def ban_ip(db: AsyncSession, ip: str, reason: str, duration_minutes: int = 60) -> bool:
    existing = await db.execute(select(IPBan).where(IPBan.ip_address == ip))
    if existing.scalar_one_or_none():
        return False
    ban_entry = IPBan(
        ip_address=ip,
        reason=reason,
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=duration_minutes),
    )
    db.add(ban_entry)
    await db.commit()
    _IP_BAN_CACHE.pop(ip, None)
    return True


async def get_banned_ips(db: AsyncSession) -> list[IPBan]:
    result = await db.execute(select(IPBan).order_by(IPBan.banned_at.desc()))
    return cast(list[IPBan], result.scalars().all())


async def ban_ips_bulk(
    db: AsyncSession, ips: list[str], reason: str, duration_minutes: int = 60
) -> int:
    if not ips:
        return 0

    # Find existing IPs to avoid duplicates
    # For very large lists, consider chunking
    result = await db.execute(select(IPBan.ip_address).where(IPBan.ip_address.in_(ips)))
    existing_ips = set(result.scalars().all())

    new_ips = [ip for ip in set(ips) if ip not in existing_ips]

    if not new_ips:
        return 0

    expires = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=duration_minutes)

    db.add_all([IPBan(ip_address=ip, reason=reason, expires_at=expires) for ip in new_ips])
    await db.commit()
    for ip in new_ips:
        _IP_BAN_CACHE.pop(ip, None)
    return len(new_ips)

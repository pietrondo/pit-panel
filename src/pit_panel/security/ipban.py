"""IP ban management and brute-force protection."""

import datetime as dt
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import time
from pit_panel.db.models import IPBan, LoginAttempt

MAX_FAILED_ATTEMPTS = 5
BAN_DURATION_MINUTES = 30
FAILED_WINDOW_MINUTES = 15

# Cache: ip -> (is_banned, cached_at_monotonic_time)
_ban_cache: dict[str, tuple[bool, float]] = {}
CACHE_TTL = 30
MAX_CACHE_SIZE = 1000

def invalidate_ban_cache(ip: str | None = None) -> None:
    if ip and ip in _ban_cache:
        del _ban_cache[ip]
    elif not ip:
        _ban_cache.clear()

async def is_ip_banned(db: AsyncSession, ip: str) -> bool:
    now = time.monotonic()
    if ip in _ban_cache:
        is_banned, cached_at = _ban_cache[ip]
        if now - cached_at < CACHE_TTL:
            return is_banned

    result = await db.execute(
        select(IPBan).where(
            IPBan.ip_address == ip,
            (IPBan.expires_at.is_(None)) | (IPBan.expires_at > dt.datetime.now(dt.UTC)),
        )
    )
    is_banned = result.scalar_one_or_none() is not None

    if len(_ban_cache) >= MAX_CACHE_SIZE:
        _ban_cache.clear()
    _ban_cache[ip] = (is_banned, now)

    return is_banned


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
            invalidate_ban_cache(ip)


async def unban_ip(db: AsyncSession, ip: str, user_id: int | None = None) -> bool:
    result = await db.execute(select(IPBan).where(IPBan.ip_address == ip))
    ban = result.scalar_one_or_none()
    if ban:
        await db.delete(ban)
        await db.commit()
        invalidate_ban_cache(ip)
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
    invalidate_ban_cache(ip)
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
        invalidate_ban_cache(ip)
    return len(new_ips)

"""IP ban management and brute-force protection."""

import datetime as dt

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.db.models import IPBan, LoginAttempt

MAX_FAILED_ATTEMPTS = 5
BAN_DURATION_MINUTES = 30
FAILED_WINDOW_MINUTES = 15


async def is_ip_banned(db: AsyncSession, ip: str) -> bool:
    result = await db.execute(
        select(IPBan).where(
            IPBan.ip_address == ip,
            (IPBan.expires_at.is_(None)) | (IPBan.expires_at > dt.datetime.now(dt.UTC)),
        )
    )
    return result.scalar_one_or_none() is not None


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


async def unban_ip(db: AsyncSession, ip: str, user_id: int | None = None) -> bool:
    result = await db.execute(select(IPBan).where(IPBan.ip_address == ip))
    ban = result.scalar_one_or_none()
    if ban:
        await db.delete(ban)
        await db.commit()
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
    return True


async def get_banned_ips(db: AsyncSession) -> list[IPBan]:
    result = await db.execute(select(IPBan).order_by(IPBan.banned_at.desc()))
    return result.scalars().all()


async def get_recent_attempts(db: AsyncSession, limit: int = 50) -> list[LoginAttempt]:
    result = await db.execute(
        select(LoginAttempt).order_by(LoginAttempt.attempted_at.desc()).limit(limit)
    )
    return result.scalars().all()


async def cleanup_expired_bans(db: AsyncSession) -> int:

    result = await db.execute(
        delete(IPBan).where(
            IPBan.expires_at.isnot(None),
            IPBan.expires_at < dt.datetime.now(dt.UTC),
        )
    )
    if result.rowcount > 0:
        await db.commit()
    return result.rowcount


async def cleanup_old_attempts(db: AsyncSession, days: int = 30) -> int:
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)

    result = await db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff))
    await db.commit()
    return result.rowcount

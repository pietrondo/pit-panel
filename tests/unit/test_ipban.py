import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.db.models import Base, IPBan, LoginAttempt


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        yield db


class TestIPBanModel:
    @pytest.mark.asyncio
    async def test_create_ban(self, db_session):
        ban = IPBan(ip_address="10.0.0.5", reason="test", failed_attempts=3)
        db_session.add(ban)
        await db_session.commit()
        await db_session.refresh(ban)

        assert ban.id is not None
        assert ban.ip_address == "10.0.0.5"
        assert ban.reason == "test"
        assert ban.failed_attempts == 3

    @pytest.mark.asyncio
    async def test_ban_expiry(self, db_session):
        expires = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30)
        ban = IPBan(ip_address="10.0.0.6", reason="auto", expires_at=expires)
        db_session.add(ban)
        await db_session.commit()

        result = await db_session.execute(select(IPBan).where(IPBan.ip_address == "10.0.0.6"))
        fetched = result.scalar_one_or_none()
        assert fetched is not None
        assert fetched.expires_at is not None


class TestLoginAttemptModel:
    @pytest.mark.asyncio
    async def test_create_attempt(self, db_session):
        attempt = LoginAttempt(ip_address="1.2.3.4", username="admin", success=False)
        db_session.add(attempt)
        await db_session.commit()
        await db_session.refresh(attempt)

        assert attempt.id is not None
        assert not attempt.success
        assert attempt.username == "admin"

    @pytest.mark.asyncio
    async def test_multiple_attempts(self, db_session):
        for _ in range(5):
            db_session.add(LoginAttempt(ip_address="5.5.5.5", username="user", success=False))
        await db_session.commit()

        result = await db_session.execute(
            select(LoginAttempt).where(LoginAttempt.ip_address == "5.5.5.5")
        )
        assert len(result.scalars().all()) == 5


class TestIPBanLogic:
    @pytest.mark.asyncio
    async def test_is_ip_banned_false(self, db_session):
        from pit_panel.security.ipban import is_ip_banned

        banned = await is_ip_banned(db_session, "10.0.0.1")
        assert not banned

    @pytest.mark.asyncio
    async def test_is_ip_banned_true(self, db_session):
        from pit_panel.security.ipban import is_ip_banned

        ban = IPBan(ip_address="10.0.0.2", reason="test", failed_attempts=5)
        db_session.add(ban)
        await db_session.commit()

        banned = await is_ip_banned(db_session, "10.0.0.2")
        assert banned

    @pytest.mark.asyncio
    async def test_record_login_failure_triggers_ban(self, db_session):
        from pit_panel.security.ipban import is_ip_banned, record_login_attempt

        for _ in range(5):
            await record_login_attempt(db_session, "192.168.1.100", "admin", False)

        banned = await is_ip_banned(db_session, "192.168.1.100")
        assert banned

    @pytest.mark.asyncio
    async def test_successful_login_no_ban(self, db_session):
        from pit_panel.security.ipban import is_ip_banned, record_login_attempt

        await record_login_attempt(db_session, "192.168.1.200", "admin", True)
        await record_login_attempt(db_session, "192.168.1.200", "admin", False)

        banned = await is_ip_banned(db_session, "192.168.1.200")
        assert not banned

    @pytest.mark.asyncio
    async def test_unban_ip(self, db_session):
        from pit_panel.security.ipban import is_ip_banned, unban_ip

        ban = IPBan(ip_address="10.0.0.99", reason="test")
        db_session.add(ban)
        await db_session.commit()

        assert await is_ip_banned(db_session, "10.0.0.99")
        await unban_ip(db_session, "10.0.0.99")
        assert not await is_ip_banned(db_session, "10.0.0.99")

    @pytest.mark.asyncio
    async def test_get_banned_ips(self, db_session):
        from pit_panel.security.ipban import get_banned_ips

        db_session.add(IPBan(ip_address="10.0.0.10", reason="a"))
        db_session.add(IPBan(ip_address="10.0.0.11", reason="b"))
        await db_session.commit()

        bans = await get_banned_ips(db_session)
        assert len(bans) == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired_bans(self, db_session):
        from pit_panel.security.ipban import cleanup_expired_bans, is_ip_banned

        past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
        ban = IPBan(ip_address="10.0.0.50", reason="old", expires_at=past)
        db_session.add(ban)
        await db_session.commit()

        removed = await cleanup_expired_bans(db_session)
        assert removed >= 1
        assert not await is_ip_banned(db_session, "10.0.0.50")

    @pytest.mark.asyncio
    async def test_cleanup_old_attempts(self, db_session):
        from pit_panel.security.ipban import cleanup_old_attempts

        old = dt.datetime.now(dt.UTC) - dt.timedelta(days=60)
        attempt = LoginAttempt(ip_address="1.1.1.1", username="x", success=False)
        attempt.attempted_at = old
        db_session.add(attempt)
        await db_session.commit()

        removed = await cleanup_old_attempts(db_session, days=30)
        assert removed >= 1


class TestSecurityApp:
    def test_security_routes_registered(self, settings):
        from pit_panel.web.app import create_app

        app = create_app(settings)
        paths = list(app.openapi()["paths"].keys())
        assert "/security" in paths
        assert "/security/unban" in paths
        assert "/security/revoke-session" in paths


class TestSystemApp:
    def test_system_routes_registered(self, settings):
        from pit_panel.web.app import create_app

        app = create_app(settings)
        paths = list(app.openapi()["paths"].keys())
        assert "/system" in paths
        assert "/system/upgrade" in paths

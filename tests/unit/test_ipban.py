import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.db.models import Base, IPBan, LoginAttempt, User
from pit_panel.security.ipban import ban_ip, is_ip_banned


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


class TestSecurityApp:
    def test_security_routes_registered(self, settings):
        from pit_panel.web.app import create_app

        app = create_app(settings)
        paths = list(app.openapi()["paths"].keys())
        assert "/security" in paths
        assert "/security/unban" in paths
        assert "/security/revoke-session" in paths
        assert "/security/ban-ip" in paths

    @pytest.mark.asyncio
    async def test_security_overview_degrades_when_db_panels_fail(self, monkeypatch):
        from pit_panel.web.routes import security

        class BrokenDb:
            def __init__(self):
                self.rollback_calls = 0

            async def execute(self, *args, **kwargs):
                raise RuntimeError("missing table")

            async def rollback(self):
                self.rollback_calls += 1

        async def mock_firewall_status():
            return {"active": False, "rules": []}

        async def mock_fail2ban_status():
            return {"active": False, "jails": []}

        monkeypatch.setattr(security, "_firewall_status", mock_firewall_status)
        monkeypatch.setattr(security, "_fail2ban_status", mock_fail2ban_status)

        db = BrokenDb()
        response = await security._render_security_page(
            None,
            db,
            User(id=1, username="admin", is_admin=True),
        )

        assert response.status_code == 200
        assert "Security" in response.body.decode()
        assert db.rollback_calls >= 1


@pytest.mark.asyncio
async def test_ban_ip_adds_record(db_session):
    result = await ban_ip(db_session, "1.2.3.4", "test ban", 60)
    assert result is True

    banned = await is_ip_banned(db_session, "1.2.3.4")
    assert banned is True


@pytest.mark.asyncio
async def test_ban_ip_duplicate_rejected(db_session):
    await ban_ip(db_session, "1.2.3.4", "first", 60)
    result = await ban_ip(db_session, "1.2.3.4", "second", 120)
    assert result is False


@pytest.mark.asyncio
async def test_ban_ip_no_expiry(db_session):
    await ban_ip(db_session, "5.6.7.8", "permanent", duration_minutes=60)
    check = await db_session.execute(select(IPBan).where(IPBan.ip_address == "5.6.7.8"))
    ban = check.scalar_one_or_none()
    assert ban is not None
    assert ban.reason == "permanent"


class TestSystemApp:
    def test_system_routes_registered(self, settings):
        from pit_panel.web.app import create_app

        app = create_app(settings)
        paths = list(app.openapi()["paths"].keys())
        assert "/system" in paths
        assert "/system/upgrade" in paths


@pytest.mark.asyncio
async def test_ban_ips_bulk(db_session):
    from pit_panel.security.ipban import ban_ips_bulk, is_ip_banned

    ips = ["1.1.1.1", "1.1.1.2", "1.1.1.3"]
    count = await ban_ips_bulk(db_session, ips, "bulk test")

    assert count == 3
    for ip in ips:
        assert await is_ip_banned(db_session, ip)

    # Test duplicates
    ips2 = ["1.1.1.2", "1.1.1.4"]
    count2 = await ban_ips_bulk(db_session, ips2, "bulk test 2")

    assert count2 == 1
    assert await is_ip_banned(db_session, "1.1.1.4")

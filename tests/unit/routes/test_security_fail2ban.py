"""Tests for fail2ban security routes."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pit_panel.web.routes.security_fail2ban as sf2b
from pit_panel.web.routes.security_fail2ban import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_admin(monkeypatch):
    mock = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr(sf2b, "get_admin", mock)
    return mock


@pytest.fixture
def mock_no_admin(monkeypatch):
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(sf2b, "get_admin", mock)
    return mock


@pytest.mark.asyncio
async def test_fail2ban_enable_unauthorized(app, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/enable", data={"jail": "sshd"})
        assert resp.status_code == 401
        assert resp.text == "Unauthorized"


@pytest.mark.asyncio
async def test_fail2ban_enable_invalid_jail(app, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/enable", data={"jail": "invalid jail"})
        assert resp.status_code == 400
        assert "Invalid jail name" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_enable_success(app, mock_admin, monkeypatch):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"stdout", b"stderr"))
    mock_proc.returncode = 0
    import asyncio

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/enable", data={"jail": "sshd"})
        assert resp.status_code == 200
        assert "sshd enabled" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_enable_failure(app, mock_admin, monkeypatch):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"stdout", b"error message"))
    mock_proc.returncode = 1
    import asyncio

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/enable", data={"jail": "sshd"})
        assert resp.status_code == 200
        assert "error message" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_enable_not_found(app, mock_admin, monkeypatch):
    import asyncio

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/enable", data={"jail": "sshd"})
        assert resp.status_code == 200
        assert "fail2ban-client not found" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_enable_exception(app, mock_admin, monkeypatch):
    import asyncio

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(side_effect=Exception("Test Error"))
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/enable", data={"jail": "sshd"})
        assert resp.status_code == 200
        assert "Error: Test Error" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_jail_unauthorized(app, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security/fail2ban/jail/sshd")
        assert resp.status_code == 401
        assert resp.text == "Unauthorized"


@pytest.mark.asyncio
async def test_fail2ban_jail_invalid(app, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security/fail2ban/jail/invalid jail")
        assert resp.status_code == 400
        assert "Invalid jail name" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_jail_empty(app, mock_admin, monkeypatch):
    monkeypatch.setattr(sf2b, "_fail2ban_jail_banned", AsyncMock(return_value=[]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security/fail2ban/jail/sshd")
        assert resp.status_code == 200
        assert "Nessun IP bloccato in" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_jail_populated(app, mock_admin, monkeypatch):
    monkeypatch.setattr(sf2b, "_fail2ban_jail_banned", AsyncMock(return_value=[{"ip": "1.2.3.4"}]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security/fail2ban/jail/sshd")
        assert resp.status_code == 200
        assert "1.2.3.4" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_unban_unauthorized(app, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/unban", data={"jail": "sshd", "ip": "1.2.3.4"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_fail2ban_unban_invalid_jail(app, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/unban", data={"jail": "inv jail", "ip": "1.2.3.4"})
        assert resp.status_code == 400
        assert "Invalid jail name" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_unban_invalid_ip(app, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/unban", data={"jail": "sshd", "ip": "invalid_ip"})
        assert resp.status_code == 400
        assert "Invalid IP address" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_unban_success(app, mock_admin, monkeypatch):
    monkeypatch.setattr(sf2b, "_fail2ban_unban", AsyncMock(return_value=True))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/unban", data={"jail": "sshd", "ip": "1.2.3.4"})
        assert resp.status_code == 200
        assert "sbloccato" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_unban_failure(app, mock_admin, monkeypatch):
    monkeypatch.setattr(sf2b, "_fail2ban_unban", AsyncMock(return_value=False))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/security/fail2ban/unban", data={"jail": "sshd", "ip": "1.2.3.4"})
        assert resp.status_code == 200
        assert "Impossibile sbloccare" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_get_config_unauthorized(app, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security/fail2ban/config/sshd")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_fail2ban_get_config_invalid_jail(app, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security/fail2ban/config/inv jail")
        assert resp.status_code == 400
        assert "Invalid jail name" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_get_config_success(app, mock_admin, monkeypatch):
    monkeypatch.setattr(sf2b, "_get_jail_config", AsyncMock(return_value={"bantime": 3600}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security/fail2ban/config/sshd")
        assert resp.status_code == 200
        assert resp.json() == {"bantime": 3600}


@pytest.mark.asyncio
async def test_fail2ban_config_unauthorized(app, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/security/fail2ban/config/sshd", data={"bantime": 3600, "findtime": 600, "maxretry": 5}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_fail2ban_config_invalid_jail(app, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/security/fail2ban/config/inv jail",
            data={"bantime": 3600, "findtime": 600, "maxretry": 5},
        )
        assert resp.status_code == 400
        assert "Invalid jail name" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_config_success(app, mock_admin, monkeypatch):
    monkeypatch.setattr(sf2b, "_save_jail_config", AsyncMock(return_value=True))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/security/fail2ban/config/sshd", data={"bantime": 3600, "findtime": 600, "maxretry": 5}
        )
        assert resp.status_code == 200
        assert "Configuration saved" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_config_failure(app, mock_admin, monkeypatch):
    monkeypatch.setattr(sf2b, "_save_jail_config", AsyncMock(return_value=False))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/security/fail2ban/config/sshd", data={"bantime": 3600, "findtime": 600, "maxretry": 5}
        )
        assert resp.status_code == 200
        assert "Failed to save configuration" in resp.text


@pytest.mark.asyncio
async def test_fail2ban_config_value_error(app, mock_admin, monkeypatch):
    monkeypatch.setattr(
        sf2b, "_save_jail_config", AsyncMock(side_effect=ValueError("Invalid config values"))
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/security/fail2ban/config/sshd", data={"bantime": 3600, "findtime": 600, "maxretry": 5}
        )
        assert resp.status_code == 400
        assert "Invalid config values" in resp.text

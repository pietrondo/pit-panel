from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from pit_panel.web.routes.security import router


@pytest.mark.asyncio
async def test_security_ban_ip(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_ban_ip_address = AsyncMock()
    mock_ban_ip_address.return_value = True
    monkeypatch.setattr("pit_panel.web.routes.security.ban_ip_address", mock_ban_ip_address)

    mock_render = AsyncMock()
    mock_render.return_value = HTMLResponse("mocked security page")
    monkeypatch.setattr("pit_panel.web.routes.security._render_security_page", mock_render)

    response = client.post(
        "/security/ban-ip", data={"ip": "1.2.3.4", "reason": "test", "duration": "60"}
    )

    assert response.status_code == 200
    assert response.text == "mocked security page"
    mock_ban_ip_address.assert_called_once()


@pytest.mark.asyncio
async def test_security_ban_ip_invalid(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = client.post("/security/ban-ip", data={"ip": "invalid-ip"})

    assert response.status_code == 400
    assert "Invalid IP address" in response.text


@pytest.mark.asyncio
async def test_security_unban(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_unban_ip_address = AsyncMock()
    mock_unban_ip_address.return_value = True
    monkeypatch.setattr("pit_panel.web.routes.security.unban_ip_address", mock_unban_ip_address)

    mock_render = AsyncMock()
    mock_render.return_value = HTMLResponse("mocked security page")
    monkeypatch.setattr("pit_panel.web.routes.security._render_security_page", mock_render)

    response = client.post("/security/unban", data={"ip": "1.2.3.4"})

    assert response.status_code == 200
    assert response.text == "mocked security page"
    mock_unban_ip_address.assert_called_once()


@pytest.mark.asyncio
async def test_security_blocklist_page(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = client.get("/security/blocklist")

    assert response.status_code == 200
    assert "FireHOL Level 1" in response.text


@pytest.mark.asyncio
async def test_security_blocklist_import(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_fetch_blocklist = AsyncMock()
    mock_fetch_blocklist.return_value = ["192.168.1.1"]
    monkeypatch.setattr("pit_panel.web.routes.security.fetch_blocklist", mock_fetch_blocklist)

    mock_ban_ips_bulk = AsyncMock()
    mock_ban_ips_bulk.return_value = 1
    monkeypatch.setattr("pit_panel.web.routes.security.ban_ips_bulk", mock_ban_ips_bulk)

    response = client.post("/security/blocklist/import", data={"source": "firehol_level1"})

    assert response.status_code == 200
    assert "Imported 1/1 IPs" in response.text


@pytest.mark.asyncio
async def test_fail2ban_enable(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = client.post("/security/fail2ban/enable", data={"jail": "sshd"})

    assert response.status_code == 200
    assert "Enabled sshd" in response.text


@pytest.mark.asyncio
async def test_fail2ban_enable_unauthorized(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = None
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = client.post("/security/fail2ban/enable", data={"jail": "sshd"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_abuseipdb_blacklist_no_key(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.abuseipdb_api_key = ""
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    response = client.get("/security/abuseipdb-blacklist")

    assert response.status_code == 200
    assert "No AbuseIPDB API key configured" in response.text


@pytest.mark.asyncio
async def test_abuseipdb_blacklist_with_data(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.abuseipdb_api_key = "test-key"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_blacklist = AsyncMock()
    mock_blacklist.return_value = [
        {"ip": "1.2.3.4", "score": 95, "reports": 10},
        {"ip": "5.6.7.8", "score": 50, "reports": 3},
    ]
    monkeypatch.setattr("pit_panel.web.routes.security._abuseipdb_blacklist", mock_blacklist)

    response = client.get("/security/abuseipdb-blacklist")

    assert response.status_code == 200
    assert "1.2.3.4" in response.text
    assert "5.6.7.8" in response.text
    assert "95" in response.text


@pytest.mark.asyncio
async def test_abuseipdb_blacklist_empty(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.abuseipdb_api_key = "test-key"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_blacklist = AsyncMock()
    mock_blacklist.return_value = []
    monkeypatch.setattr("pit_panel.web.routes.security._abuseipdb_blacklist", mock_blacklist)

    response = client.get("/security/abuseipdb-blacklist")

    assert response.status_code == 200
    assert "No blacklist entries found" in response.text


@pytest.mark.asyncio
async def test_abuseipdb_check(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_check = AsyncMock()
    mock_check.return_value = {"ip": "1.2.3.4", "score": 85, "reports": 5}
    monkeypatch.setattr("pit_panel.web.routes.security._abuseipdb_check", mock_check)

    response = client.post(
        "/security/abuseipdb-check", data={"ip": "1.2.3.4", "api_key": "test-key"}
    )

    assert response.status_code == 200
    assert "1.2.3.4" in response.text
    assert "85" in response.text


@pytest.mark.asyncio
async def test_abuseipdb_check_missing_params(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = client.post("/security/abuseipdb-check", data={"ip": "", "api_key": ""})

    assert response.status_code == 200
    assert "IP and API key are required" in response.text


@pytest.mark.asyncio
async def test_abuseipdb_check_error(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_check = AsyncMock()
    mock_check.return_value = {"ip": "1.2.3.4", "error": "API limit exceeded"}
    monkeypatch.setattr("pit_panel.web.routes.security._abuseipdb_check", mock_check)

    response = client.post(
        "/security/abuseipdb-check", data={"ip": "1.2.3.4", "api_key": "test-key"}
    )

    assert response.status_code == 200
    assert "Error: API limit exceeded" in response.text

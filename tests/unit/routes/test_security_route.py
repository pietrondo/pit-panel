from unittest.mock import AsyncMock, MagicMock, mock_open, patch

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

    class MockProcess:
        returncode = 0
        async def communicate(self, *args, **kwargs):
            return b"", b""
        def kill(self):
            pass

    async def mock_create_subprocess_exec(*args, **kwargs):
        return MockProcess()

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_create_subprocess_exec,
    )

    response = client.post("/security/fail2ban/enable", data={"jail": "sshd"})

    assert response.status_code == 200
    assert "sshd enabled" in response.text


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


@pytest.mark.asyncio
async def test_security_firewall_enable(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    mock_enable = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security._enable_ufw", mock_enable)

    response = client.post("/security/firewall/enable")
    assert response.status_code == 200
    mock_enable.assert_called_once()


@pytest.mark.asyncio
async def test_security_firewall_disable(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    mock_disable = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security._disable_ufw", mock_disable)

    response = client.post("/security/firewall/disable")
    assert response.status_code == 200
    mock_disable.assert_called_once()


@pytest.mark.asyncio
async def test_security_firewall_rule_add(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    mock_add = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security._add_ufw_rule", mock_add)

    response = client.post(
        "/security/firewall/rule/add",
        data={"port": "8080", "protocol": "tcp", "action": "allow", "source": ""}
    )
    assert response.status_code == 200
    mock_add.assert_called_once_with("8080", "tcp", "allow", "")


@pytest.mark.asyncio
async def test_security_firewall_rule_delete(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    mock_delete = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security._delete_ufw_rule", mock_delete)
    monkeypatch.setattr("pit_panel.web.routes.security._get_client_ip", lambda r: "1.2.3.4")
    monkeypatch.setattr(
        "pit_panel.web.routes.security._detect_ssh_port",
        AsyncMock(return_value=22),
    )

    response = client.post("/security/firewall/rule/delete", data={"index": "3"})
    assert response.status_code == 200
    mock_delete.assert_called_once_with(3, client_ip="1.2.3.4", ssh_port=22)


@pytest.mark.asyncio
async def test_security_fail2ban_config(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    mock_save = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security._save_jail_config", mock_save)

    response = client.post(
        "/security/fail2ban/config/sshd",
        data={"bantime": "3600", "findtime": "600", "maxretry": "5"}
    )
    assert response.status_code == 200
    mock_save.assert_called_once_with("sshd", bantime=3600, findtime=600, maxretry=5)


@pytest.mark.asyncio
async def test_security_clamav_toggle_low_memory(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_host_memory_gb",
        AsyncMock(return_value=1.5),
    )

    response = client.post("/security/malware/clamav/toggle")
    assert response.status_code == 400
    assert "Insufficient system memory" in response.text


@pytest.mark.asyncio
async def test_security_clamav_toggle_success(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_host_memory_gb",
        AsyncMock(return_value=4.0),
    )

    mock_run = AsyncMock(return_value=(b"stopped", b""))
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_run)

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(side_effect=[
        (b"", b""),             # docker ps returns not running
        (b"exists", b""),       # docker image inspect returns exists
        (b"container_id", b"")  # docker run starts container
    ])
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    response = client.post("/security/malware/clamav/toggle")
    assert response.status_code == 200
    assert "ClamAV container started" in response.text


@pytest.mark.asyncio
async def test_security_lynis_audit(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    mock_audit = AsyncMock(return_value={"hardening_index": 80})
    monkeypatch.setattr("pit_panel.web.routes.security.run_lynis_audit", mock_audit)

    response = client.post("/security/lynis/audit")
    assert response.status_code == 200
    assert "System audit started" in response.text


@pytest.mark.asyncio
async def test_security_lynis_report(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )

    mock_json = '{"hardening_index": 80, "warnings": ["w"], "suggestions": ["s"]}'
    with patch("builtins.open", mock_open(read_data=mock_json)):
        response = client.get("/security/lynis/report")
        assert response.status_code == 200
        assert "hardening_index" in response.json()
        assert response.json()["hardening_index"] == 80


@pytest.mark.asyncio
async def test_security_fail2ban_get_config(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    mock_get = AsyncMock(return_value={"bantime": 3600, "findtime": 600, "maxretry": 5})
    monkeypatch.setattr("pit_panel.web.routes.security._get_jail_config", mock_get)

    response = client.get("/security/fail2ban/config/sshd")
    assert response.status_code == 200
    assert response.json()["bantime"] == 3600
    mock_get.assert_called_once_with("sshd")

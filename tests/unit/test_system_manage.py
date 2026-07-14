from unittest.mock import ANY, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
from pit_panel.core.sudo_ops import run_sudo
from pit_panel.web.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        debug=True,
        sudo_password="test-sudo-password",
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)
    monkeypatch.setattr("pit_panel.db.session._engine", None)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", None)
    app = create_app(s)
    return TestClient(app)


@pytest.fixture
def auth_headers(monkeypatch):
    async def mock_get_admin(*args, **kwargs):
        from pit_panel.db.models import User

        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.system_manage.get_admin", mock_get_admin)
    return {}


@pytest.mark.asyncio
async def test_run_sudo_whitelist_valid():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"output\n", b"")
        mock_exec.return_value = mock_proc

        result = await run_sudo(["df", "-h"], "testpass")

        assert result == "output\n"
        mock_exec.assert_called_once_with(
            "sudo",
            "-S",
            "-p",
            "",
            "df",
            "-h",
            stdin=ANY,
            stdout=ANY,
            stderr=ANY,
        )
        mock_proc.communicate.assert_called_once_with(input=b"testpass\n")


@pytest.mark.asyncio
async def test_run_sudo_whitelist_invalid():
    with pytest.raises(ValueError, match="Command 'ls' is not allowed"):
        await run_sudo(["ls", "-la"], "testpass")


@pytest.mark.asyncio
async def test_run_sudo_empty():
    with pytest.raises(ValueError, match="Command cannot be empty"):
        await run_sudo([], "testpass")


def test_system_manage_get(client: TestClient, auth_headers: dict):
    response = client.get("/system/manage", headers=auth_headers)
    assert response.status_code == 200
    assert b"System Management" in response.content


def test_system_manage_get_unauthorized(client: TestClient):
    response = client.get("/system/manage", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_system_manage_action_df(client: TestClient, auth_headers: dict):
    with patch("pit_panel.web.routes.system_manage.run_sudo", new_callable=AsyncMock) as mock_sudo:
        mock_sudo.return_value = "Filesystem      Size\n/dev/sda1        50G"

        response = client.post("/system/manage/action", data={"action": "df"}, headers=auth_headers)

        assert response.status_code == 200
        assert b"Filesystem" in response.content
        expected = ["/usr/bin/df", "-h"]
        mock_sudo.assert_called_once_with(expected, client.app.state.settings.sudo_password)


def test_system_manage_action_reboot(client: TestClient, auth_headers: dict):
    with patch("pit_panel.web.routes.system_manage.run_sudo", new_callable=AsyncMock) as mock_sudo:
        mock_sudo.return_value = "System is going down for reboot NOW!"

        response = client.post(
            "/system/manage/action", data={"action": "reboot"}, headers=auth_headers
        )

        assert response.status_code == 200
        assert b"reboot NOW!" in response.content
        expected = ["/usr/sbin/reboot"]
        mock_sudo.assert_called_once_with(expected, client.app.state.settings.sudo_password)


def test_system_manage_action_invalid(client: TestClient, auth_headers: dict):
    response = client.post(
        "/system/manage/action", data={"action": "hack_system"}, headers=auth_headers
    )

    assert response.status_code == 400
    assert b"Unknown action" in response.content


def test_system_manage_action_unauthorized(client: TestClient):
    response = client.post("/system/manage/action", data={"action": "df"})

    assert response.status_code == 401


def test_system_manage_action_no_sudo_password(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(client.app.state.settings, "sudo_password", "")
    response = client.post("/system/manage/action", data={"action": "df"}, headers=auth_headers)
    assert response.status_code == 200
    assert b"sudo_password is not configured" in response.content


def test_system_manage_services_no_nginx(client: TestClient, auth_headers: dict):
    with patch("pit_panel.web.routes.system_manage.run_sudo", new_callable=AsyncMock) as mock_sudo:
        mock_sudo.return_value = "active"

        response = client.get("/system/manage/services", headers=auth_headers)

        assert response.status_code == 200
        assert b"Caddy" in response.content
        assert b"Pit Panel" in response.content
        assert b"Nginx" not in response.content
        assert b"nginx" not in response.content

def test_resolve_cmd_safe_service_validation() -> None:
    from pit_panel.web.routes.system_manage import _resolve_cmd

    with patch("pit_panel.web.routes.system_manage.SERVICES", [
        ("valid-service-123", "Valid"),
        ("also_valid", "Also Valid"),
        ("-invalid-starts-with-dash", "Invalid 1"),
        ("invalid;injection", "Invalid 2"),
        ("invalid space", "Invalid 3"),
    ]):
        # Test valid ones
        assert _resolve_cmd("service_restart_valid-service-123") == ["/usr/bin/systemctl", "restart", "--", "valid-service-123"]
        assert _resolve_cmd("service_stop_also_valid") == ["/usr/bin/systemctl", "stop", "--", "also_valid"]
        assert _resolve_cmd("service_start_valid-service-123") == ["/usr/bin/systemctl", "start", "--", "valid-service-123"]
        assert _resolve_cmd("journal_also_valid") == ["/usr/bin/journalctl", "-u", "also_valid", "-n", "100", "--no-pager"]

        # Test invalid ones that shouldn't be executed due to `is_safe` filtering
        assert _resolve_cmd("service_restart_-invalid-starts-with-dash") is None
        assert _resolve_cmd("service_restart_invalid;injection") is None
        assert _resolve_cmd("service_restart_invalid space") is None

        # Test completely non-existent service
        assert _resolve_cmd("service_restart_non-existent") is None

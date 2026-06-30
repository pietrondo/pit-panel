"""Tests for app_routes/ops.py — restart, stop, delete, status, containers, env."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import User
from pit_panel.web.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)
    monkeypatch.setattr("pit_panel.db.session._engine", None)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", None)
    app = create_app(s)
    return TestClient(app)


def _setup_session(client, monkeypatch, mock_sd=None):
    from pit_panel.db.session import get_db

    async def mock_get_user(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.app_routes.ops.get_user", mock_get_user)

    class MockSD:
        id = 1
        subdomain = "blog"
        base_domain = "example.com"
        is_main_domain = False
        app_type = "wordpress"
        last_deployed = None

    sd = mock_sd or MockSD()

    class MockResult:
        def scalar_one_or_none(self):
            return sd

    class MockSession:
        async def execute(self, *args, **kwargs):
            return MockResult()

        async def close(self):
            pass

        async def commit(self):
            pass

        def add(self, obj):
            pass

    async def override_get_db():
        yield MockSession()

    client.app.dependency_overrides[get_db] = override_get_db
    return sd


def test_restart_authenticated(client, monkeypatch):
    _setup_session(client, monkeypatch)
    mock_compose = AsyncMock()
    monkeypatch.setattr(
        "pit_panel.core.docker_ops.DockerManager.run_compose_command", mock_compose
    )

    try:
        resp = client.post("/apps/1/restart", follow_redirects=False)
        assert resp.status_code == 200
        assert resp.headers.get("HX-Redirect") == "/apps/1"
        mock_compose.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_stop_authenticated(client, monkeypatch):
    _setup_session(client, monkeypatch)
    mock_compose = AsyncMock()
    monkeypatch.setattr(
        "pit_panel.core.docker_ops.DockerManager.run_compose_command", mock_compose
    )

    try:
        resp = client.post("/apps/1/stop", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/apps"
    finally:
        client.app.dependency_overrides.clear()


def test_delete_authenticated(client, monkeypatch):
    from pit_panel.config import Settings

    _setup_session(client, monkeypatch)
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.ops.get_settings",
        lambda: Settings(secret_key="test", base_domain="example.com"),
    )
    mock_compose = AsyncMock()
    monkeypatch.setattr(
        "pit_panel.core.docker_ops.DockerManager.run_compose_command", mock_compose
    )
    mock_remove = AsyncMock()
    monkeypatch.setattr(
        "pit_panel.core.caddy.CaddyManager.remove_subdomain", mock_remove
    )

    try:
        resp = client.post("/apps/1/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/apps"
    finally:
        client.app.dependency_overrides.clear()


def test_status_authenticated(client, monkeypatch):
    _setup_session(client, monkeypatch)
    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.compose_ps.return_value = [
        {"Name": "blog-web", "State": "running", "Status": "Up 2 hours"},
        {"Name": "blog-db", "State": "exited", "Status": "Exited (0)"},
    ]
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.ops.DockerManager", lambda *args: mock_docker_mgr
    )

    try:
        resp = client.get("/apps/1/status")
        assert resp.status_code == 200
        assert "Active" in resp.text
        assert "1/2" in resp.text
    finally:
        client.app.dependency_overrides.clear()


def test_update_authenticated(client, monkeypatch):
    _setup_session(client, monkeypatch)
    mock_compose = AsyncMock()
    mock_compose.return_value = {"success": True}
    monkeypatch.setattr(
        "pit_panel.core.docker_ops.DockerManager.run_compose_command", mock_compose
    )

    try:
        resp = client.post("/apps/1/update", follow_redirects=False)
        assert resp.status_code == 200
        assert resp.headers.get("HX-Redirect") == "/apps/1"
        assert mock_compose.call_count == 2  # pull + up -d
    finally:
        client.app.dependency_overrides.clear()


def test_containers_requires_login(client):
    resp = client.get("/apps/1/containers", follow_redirects=False)
    assert resp.status_code in (200, 302)
    if resp.status_code == 200:
        assert resp.headers.get("HX-Redirect") == "/login"


def test_env_get_authenticated(client, monkeypatch, tmp_path):
    from pit_panel.config import Settings

    sd = _setup_session(client, monkeypatch)
    app_dir = tmp_path / "apps" / sd.subdomain
    app_dir.mkdir(parents=True)
    env_file = app_dir / ".env"
    env_file.write_text("KEY=value\nPORT=8081\n")

    settings = Settings(secret_key="test", apps_dir=str(tmp_path / "apps"))
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.ops.get_settings", lambda: settings
    )

    try:
        resp = client.get("/apps/1/env")
        assert resp.status_code == 200
        assert "KEY=value" in resp.text
    finally:
        client.app.dependency_overrides.clear()


def test_env_post_authenticated(client, monkeypatch, tmp_path):
    from pit_panel.config import Settings

    sd = _setup_session(client, monkeypatch)
    app_dir = tmp_path / "apps" / sd.subdomain
    app_dir.mkdir(parents=True)

    settings = Settings(secret_key="test", apps_dir=str(tmp_path / "apps"))
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.ops.get_settings", lambda: settings
    )

    try:
        resp = client.post("/apps/1/env", data={"env_content": "NEW_KEY=hello\n"})
        assert resp.status_code == 200
        assert ".env file" in resp.text.lower() or "success" in resp.text.lower()
    finally:
        client.app.dependency_overrides.clear()

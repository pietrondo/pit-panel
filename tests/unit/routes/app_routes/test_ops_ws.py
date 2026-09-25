from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(settings):
    from pit_panel.web.app import create_app

    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def settings():
    from pit_panel.config import Settings

    return Settings(secret_key="test", base_domain="example.com")


def _setup_session(client, monkeypatch, mock_sd=None):
    from pit_panel.db.models import Subdomain, User
    from pit_panel.db.session import get_db

    async def mock_get_user(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    if not mock_sd:
        mock_sd = Subdomain(id=1, subdomain="blog", base_domain="example.com", owner_user_id=1)

    class MockScalars:
        def all(self):
            return [mock_sd]

        def first(self):
            return mock_sd

        def one_or_none(self):
            return mock_sd

    class MockResult:
        def scalars(self):
            return MockScalars()

        def scalar_one_or_none(self):
            return mock_sd

    async def mock_execute(*args, **kwargs):
        return MockResult()

    mock_db = AsyncMock()
    mock_db.execute = mock_execute
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = AsyncMock()

    client.app.dependency_overrides[get_db] = lambda: mock_db

    import pit_panel.web.deps as deps

    monkeypatch.setattr(deps, "get_current_user", mock_get_user)
    if hasattr(deps, "get_current_user_ws"):
        monkeypatch.setattr(deps, "get_current_user_ws", mock_get_user)
    else:

        async def mock_get_current_user_ws(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        client.app.dependency_overrides[deps.get_current_user] = mock_get_current_user_ws

    return mock_sd


def test_terminal_ws_authenticated(client, monkeypatch, tmp_path):
    import pit_panel.web.routes.app_routes.ops as ops
    from pit_panel.config import Settings

    sd = _setup_session(client, monkeypatch)
    app_dir = tmp_path / "apps" / sd.subdomain
    app_dir.mkdir(parents=True)
    compose = app_dir / "docker-compose.yml"
    compose.write_text("services:\n  web:\n    image: nginx\n")

    settings = Settings(secret_key="test", apps_dir=str(tmp_path / "apps"))
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.ops_terminal.get_settings", lambda: settings
    )

    mock_proc = AsyncMock()
    mock_proc.stdout.read = AsyncMock(side_effect=[b"hello", b""])
    mock_proc.stdin = AsyncMock()
    mock_proc.stdin.write = AsyncMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.kill = AsyncMock()
    mock_proc.stdin.is_closing = lambda: False

    async def mock_create_subprocess_exec(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)

    with client.websocket_connect("/apps/1/terminal/ws") as websocket:
        data = websocket.receive_text()
        assert data == "hello"
        websocket.send_text("ls\n")

    mock_proc_err = AsyncMock()
    mock_proc_err.stdout.read = AsyncMock(side_effect=[b"hello", b""])

    async def mock_create_subprocess_exec_err(*args, **kwargs):
        raise OSError("Failed to run")

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec_err)

    with client.websocket_connect("/apps/1/terminal/ws") as websocket:
        data = websocket.receive_text()
        assert "ERROR: Failed to run" in data

    async def mock_execute_none(*args, **kwargs):
        class MockResultNone:
            def scalar_one_or_none(self):
                return None

        return MockResultNone()

    mock_db = client.app.dependency_overrides[ops.get_db]()
    mock_db.execute = mock_execute_none

    with client.websocket_connect("/apps/999/terminal/ws") as websocket:
        data = websocket.receive_text()
        assert "ERROR: App not found" in data


def test_logs_ws_authenticated(client, monkeypatch, tmp_path):
    from pit_panel.config import Settings

    sd = _setup_session(client, monkeypatch)
    app_dir = tmp_path / "apps" / sd.subdomain
    app_dir.mkdir(parents=True)
    compose = app_dir / "docker-compose.yml"
    compose.write_text("services:\n  web:\n    image: nginx\n")

    settings = Settings(secret_key="test", apps_dir=str(tmp_path / "apps"))
    monkeypatch.setattr("pit_panel.web.routes.app_routes.ops_files.get_settings", lambda: settings)

    mock_proc = AsyncMock()
    mock_proc.stdout.read = AsyncMock(side_effect=[b"log line 1\n", b"log line 2\n", b""])
    mock_proc.kill = AsyncMock()

    async def mock_create_subprocess_exec(*args, **kwargs):
        assert "logs" in args
        assert "--follow" in args
        return mock_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)

    with client.websocket_connect("/apps/1/logs/ws") as websocket:
        data = websocket.receive_text()
        assert data == "log line 1\n"
        data2 = websocket.receive_text()
        assert data2 == "log line 2\n"

    mock_proc_err = AsyncMock()
    mock_proc_err.stdout.read = AsyncMock(side_effect=[b"hello", b""])

    async def mock_create_subprocess_exec_err(*args, **kwargs):
        raise OSError("Failed to run logs")

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec_err)

    with client.websocket_connect("/apps/1/logs/ws") as websocket:
        data = websocket.receive_text()
        assert "ERROR: Failed to run logs" in data

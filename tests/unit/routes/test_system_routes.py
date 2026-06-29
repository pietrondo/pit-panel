import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from pit_panel.db.models import UpdateHistory, User
from pit_panel.web.routes.system import _get_git_info, _run, _sudo, system_page, system_upgrade


@pytest.mark.asyncio
async def test_system_page_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    response = await system_page(mock_request, mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_system_upgrade_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    response = await system_upgrade(mock_request, mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_system_page_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    async def mock_git_info():
        return "1234567", "7654321"

    monkeypatch.setattr("pit_panel.web.routes.system._get_git_info", mock_git_info)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.system.render", mock_render)

    mock_result = MagicMock()
    mock_update = MagicMock(spec=UpdateHistory)
    mock_result.scalars.return_value.all.return_value = [mock_update]
    mock_db.execute.return_value = mock_result

    await system_page(mock_request, mock_db)

    mock_render.assert_called_once_with(
        "system.html",
        user=user,
        current_version="1234567",
        remote_version="7654321",
        update_available=True,
        update_history=[mock_update],
        upgrade_result=None,
    )
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_git_info_success(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 0
    mock_proc_local.communicate.return_value = (b"1234567\n", b"")

    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 0
    mock_proc_remote.communicate.return_value = (b"7654321098\n", b"")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    current, remote = await _get_git_info()

    assert current == "1234567"
    assert remote == "7654321"


@pytest.mark.asyncio
async def test_get_git_info_local_fail(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 1
    mock_proc_local.communicate.return_value = (b"", b"error")

    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 0
    mock_proc_remote.communicate.return_value = (b"7654321098\n", b"")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    current, remote = await _get_git_info()

    assert current == "unknown"
    assert remote == "7654321"


@pytest.mark.asyncio
async def test_get_git_info_remote_git_fail_http_success(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 0
    mock_proc_local.communicate.return_value = (b"1234567\n", b"")

    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 1
    mock_proc_remote.communicate.return_value = (b"", b"error")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    class MockResponse:
        status_code = 200

        def json(self):
            return {"sha": "abcdef12345"}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    current, remote = await _get_git_info()

    assert current == "1234567"
    assert remote == "abcdef1"


@pytest.mark.asyncio
async def test_get_git_info_remote_git_fail_http_fail(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 0
    mock_proc_local.communicate.return_value = (b"1234567\n", b"")

    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 1
    mock_proc_remote.communicate.return_value = (b"", b"error")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, *args, **kwargs):
            raise Exception("Network error")

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    current, remote = await _get_git_info()

    assert current == "1234567"
    assert remote == "unknown"


@pytest.mark.asyncio
async def test_system_upgrade_authenticated_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mock_run_result.stdout = "ok"
    mock_run_result.stderr = ""

    def mock_sudo(cmd, timeout=60):
        return mock_run_result

    def mock_run(cmd, timeout=60):
        return mock_run_result

    monkeypatch.setattr("pit_panel.web.routes.system._sudo", mock_sudo)
    monkeypatch.setattr("pit_panel.web.routes.system._run", mock_run)

    async def mock_git_info():
        return "1234567", "7654321"

    monkeypatch.setattr("pit_panel.web.routes.system._get_git_info", mock_git_info)

    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.system.render", mock_render)

    await system_upgrade(mock_request, mock_db)

    mock_db.add.assert_called_once()
    assert mock_db.add.call_args[0][0].status == "completed"
    mock_db.commit.assert_called_once()

    mock_popen.assert_called_once()

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["upgrade_result"] != "no steps ran"
    assert "OK" in kwargs["upgrade_result"]


@pytest.mark.asyncio
async def test_system_upgrade_authenticated_fail(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    mock_run_result = MagicMock()
    mock_run_result.returncode = 1
    mock_run_result.stdout = "fail"
    mock_run_result.stderr = "error"

    def mock_run(cmd, timeout=60):
        return mock_run_result

    monkeypatch.setattr("pit_panel.web.routes.system._run", mock_run)

    async def mock_git_info():
        return "1234567", "7654321"

    monkeypatch.setattr("pit_panel.web.routes.system._get_git_info", mock_git_info)

    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.system.render", mock_render)

    await system_upgrade(mock_request, mock_db)

    mock_db.add.assert_called_once()
    assert mock_db.add.call_args[0][0].status == "failed"
    mock_db.commit.assert_called_once()

    mock_popen.assert_not_called()

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert "FAIL" in kwargs["upgrade_result"]


@pytest.mark.asyncio
async def test_system_upgrade_db_error(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    mock_db.add.side_effect = Exception("DB Error")

    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mock_run_result.stdout = "ok"
    mock_run_result.stderr = ""

    def mock_sudo(cmd, timeout=60):
        return mock_run_result

    def mock_run(cmd, timeout=60):
        return mock_run_result

    monkeypatch.setattr("pit_panel.web.routes.system._sudo", mock_sudo)
    monkeypatch.setattr("pit_panel.web.routes.system._run", mock_run)

    async def mock_git_info():
        return "1234567", "7654321"

    monkeypatch.setattr("pit_panel.web.routes.system._get_git_info", mock_git_info)

    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.system.render", mock_render)

    await system_upgrade(mock_request, mock_db)

    mock_popen.assert_called_once()
    mock_render.assert_called_once()


def test_sudo_and_run(monkeypatch):
    mock_result = MagicMock(spec=subprocess.CompletedProcess)

    def mock_subprocess_run(cmd, *args, **kwargs):
        return mock_result

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    res1 = _sudo(["ls"])
    assert res1 == mock_result

    res2 = _run(["ls"])
    assert res2 == mock_result


@pytest.mark.asyncio
async def test_get_git_info_local_git_exception(monkeypatch):
    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 0
    mock_proc_remote.communicate.return_value = (b"7654321098\n", b"")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            raise Exception("Git command failed")
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    current, remote = await _get_git_info()

    assert current == "unknown"
    assert remote == "7654321"


@pytest.mark.asyncio
async def test_get_git_info_remote_git_exception_http_success(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 0
    mock_proc_local.communicate.return_value = (b"1234567\n", b"")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            raise Exception("Git ls-remote failed")
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    class MockResponse:
        status_code = 200

        def json(self):
            return {"sha": "abcdef12345"}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    current, remote = await _get_git_info()

    assert current == "1234567"
    assert remote == "abcdef1"


@pytest.mark.asyncio
async def test_get_git_info_remote_http_not_200(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 0
    mock_proc_local.communicate.return_value = (b"1234567\n", b"")

    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 1
    mock_proc_remote.communicate.return_value = (b"", b"error")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    class MockResponse:
        status_code = 404

        def json(self):
            return {}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    current, remote = await _get_git_info()

    assert current == "1234567"
    assert remote == "unknown"


@pytest.mark.asyncio
async def test_get_git_info_remote_git_fail_http_success_no_sha(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 0
    mock_proc_local.communicate.return_value = (b"1234567\n", b"")

    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 1
    mock_proc_remote.communicate.return_value = (b"", b"error")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    class MockResponse:
        status_code = 200

        def json(self):
            return {"sha": ""}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    current, remote = await _get_git_info()

    assert current == "1234567"
    assert remote == "unknown"


@pytest.mark.asyncio
async def test_get_git_info_remote_git_empty_stdout(monkeypatch):
    mock_proc_local = AsyncMock()
    mock_proc_local.returncode = 0
    mock_proc_local.communicate.return_value = (b"1234567\n", b"")

    mock_proc_remote = AsyncMock()
    mock_proc_remote.returncode = 0
    mock_proc_remote.communicate.return_value = (b"   \n", b"")

    async def mock_create_subprocess_exec(*args, **kwargs):
        if args[0] == "git" and args[1] == "rev-parse":
            return mock_proc_local
        elif args[0] == "git" and args[1] == "ls-remote":
            return mock_proc_remote
        return AsyncMock()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    class MockResponse:
        status_code = 404

        def json(self):
            return {}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    current, remote = await _get_git_info()

    assert current == "1234567"
    assert remote == "unknown"

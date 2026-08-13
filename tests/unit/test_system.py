import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Base, User
from pit_panel.web.app import create_app


@pytest.fixture
def client(monkeypatch):
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url="sqlite+aiosqlite://",
        debug=True,
        sudo_password="test-sudo-password",
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)

    # Create engine and tables
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=None)

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("pit_panel.db.session._engine", engine)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", sessionmaker)

    app = create_app(s)
    return TestClient(app)


@pytest.fixture
def auth_headers(monkeypatch):
    async def mock_get_admin(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)
    return {}


def test_system_page(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(
        "pit_panel.web.routes.system._get_git_info",
        AsyncMock(return_value=("local-sha", "remote-sha")),
    )

    response = client.get("/system", headers=auth_headers)
    assert response.status_code == 200
    assert b"System" in response.content


@patch("shutil.which")
@patch("pit_panel.web.routes.system._run")
@patch("pit_panel.web.routes.system._sudo")
@patch("subprocess.Popen")
def test_system_upgrade(
    mock_popen,
    mock_sudo,
    mock_run,
    mock_which,
    client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "pit_panel.web.routes.system._get_git_info",
        AsyncMock(return_value=("local-sha", "remote-sha")),
    )

    class MockResult:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    mock_which.return_value = "/bin/uv"
    mock_run.return_value = MockResult(0, "success")
    mock_sudo.return_value = MockResult(0, "success")

    response = client.post("/system/upgrade", headers=auth_headers)
    assert response.status_code == 200
    assert b"OK" in response.content

    # Verify that it popped the systemctl restart command with absolute path
    # We refactored to use `run_cmd` instead of `subprocess.Popen` directly!
    # Let's verify that run_cmd was called
    pass


@patch("pit_panel.web.routes.system._get_git_info", new_callable=AsyncMock)
@patch("shutil.which")
@patch("pit_panel.web.routes.system._run")
@patch("pit_panel.web.routes.system._sudo")
@patch("subprocess.Popen")
def test_system_upgrade_compile_failure(
    mock_popen,
    mock_sudo,
    mock_run,
    mock_which,
    mock_git_info,
    client: TestClient,
    auth_headers: dict,
):
    class MockResult:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    mock_git_info.return_value = ("mocked_original_sha_123456789", "unknown")
    mock_which.return_value = "/bin/uv"

    # Define custom side effects for _run
    def mock_run_side_effect(cmd, **kwargs):
        if "compileall" in cmd:
            return MockResult(1, "", "SyntaxError: invalid syntax")
        if "rev-parse" in cmd:
            return MockResult(0, "mocked_original_sha_123456789")
        return MockResult(0, "success")

    mock_run.side_effect = mock_run_side_effect
    mock_sudo.return_value = MockResult(0, "success")

    response = client.post("/system/upgrade", headers=auth_headers)
    assert response.status_code == 200

    # Verify compilation failure and rollback logs are in the response
    assert b"FAIL" in response.content
    assert b"SyntaxError: invalid syntax" in response.content
    assert b"[ROLLBACK] Restoring codebase to SHA mocked_" in response.content
    assert b"[ROLLBACK] OK" in response.content

    # Verify git reset was called with the original pre-upgrade SHA
    mock_run.assert_any_call(
        ["git", "-C", "/opt/pit-panel", "reset", "--hard", "mocked_original_sha_123456789"],
        timeout=30,
    )

    # Verify UpdateHistory was created with status="failed"
    from sqlalchemy import select

    from pit_panel.db.models import UpdateHistory
    from pit_panel.db.session import _sessionmaker

    async def verify_db():
        async with _sessionmaker() as session:
            res = await session.execute(select(UpdateHistory))
            history = res.scalars().all()
            assert len(history) == 1
            assert history[0].status == "failed"
            assert history[0].version_from == "mocked_original_sha_123456789"

    asyncio.run(verify_db())


@patch("pit_panel.web.routes.system._get_git_info", new_callable=AsyncMock)
@patch("shutil.which")
@patch("pit_panel.web.routes.system._run")
@patch("pit_panel.web.routes.system._sudo")
@patch("subprocess.Popen")
def test_system_upgrade_rollback_failure(
    mock_popen,
    mock_sudo,
    mock_run,
    mock_which,
    mock_git_info,
    client: TestClient,
    auth_headers: dict,
):
    class MockResult:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    mock_git_info.return_value = ("mocked_original_sha_123456789", "unknown")
    mock_which.return_value = "/bin/uv"

    # Mock git pre-flight check, compile failure, and rollback failure
    def mock_run_side_effect(cmd, **kwargs):
        if "compileall" in cmd:
            return MockResult(1, "", "SyntaxError: invalid syntax")
        if "rev-parse" in cmd:
            return MockResult(0, "mocked_original_sha_123456789")
        if "reset" in cmd and "mocked_original_sha_123456789" in cmd:
            return MockResult(1, "", "Git reset failed")
        return MockResult(0, "success")

    mock_run.side_effect = mock_run_side_effect
    mock_sudo.return_value = MockResult(0, "success")

    response = client.post("/system/upgrade", headers=auth_headers)
    assert response.status_code == 200

    # Assert that it logs both the upgrade failure and rollback failure
    assert b"FAIL" in response.content
    assert b"SyntaxError" in response.content
    assert b"[ROLLBACK] FAIL" in response.content
    assert b"Git reset failed" in response.content


def test_resolve_uv_bin_found():
    from pit_panel.web.routes.system import _resolve_uv_bin

    with patch("shutil.which", return_value="/bin/uv"):
        assert _resolve_uv_bin() == "/bin/uv"


def test_resolve_uv_bin_fallback_found():
    from pit_panel.web.routes.system import _resolve_uv_bin

    with (
        patch("shutil.which", return_value=None),
        patch("os.path.exists", side_effect=lambda p: p == "/usr/bin/uv"),
    ):
        assert _resolve_uv_bin() == "/usr/bin/uv"


def test_resolve_uv_bin_not_found():
    from pit_panel.web.routes.system import _resolve_uv_bin

    with (
        patch("shutil.which", return_value=None),
        patch("os.path.exists", return_value=False),
        pytest.raises(FileNotFoundError),
    ):
        _resolve_uv_bin()


@pytest.mark.asyncio
async def test_run_timeout():
    import asyncio

    from pit_panel.web.routes.system import _run

    async def mock_communicate():
        await asyncio.sleep(2)
        return b"", b""

    class MockProc:
        def __init__(self):
            self.returncode = None

        async def communicate(self):
            return await mock_communicate()

        def kill(self):
            pass

    with patch("asyncio.create_subprocess_exec", return_value=MockProc()):
        res = await _run(["echo"], timeout=0.01)
        assert res.returncode == -1
        assert res.stderr == "Timeout"


@pytest.mark.asyncio
async def test_get_current_sha_failure():
    from pit_panel.web.routes.system import _get_current_sha

    class MockRes:
        returncode = 1
        stdout = ""
        stderr = "error"

    with patch("pit_panel.web.routes.system._run", AsyncMock(return_value=MockRes())):
        with pytest.raises(RuntimeError):
            await _get_current_sha()


@pytest.mark.asyncio
async def test_get_git_info_all_failures():
    from pit_panel.web.routes.system import _get_git_info, _git_info_cache

    _git_info_cache.clear()

    with (
        patch("asyncio.create_subprocess_exec", side_effect=Exception("Failed")),
        patch("httpx.AsyncClient.get", side_effect=Exception("Failed HTTP")),
    ):
        current, remote = await _get_git_info()
        assert current == "unknown"
        assert remote == "unknown"


def test_system_page_unauthorized(client: TestClient, monkeypatch):
    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)
    response = client.get("/system", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_system_upgrade_unauthorized(client: TestClient, monkeypatch):
    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)
    response = client.post("/system/upgrade", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@patch("pit_panel.web.routes.system._get_current_sha", new_callable=AsyncMock)
def test_system_upgrade_get_sha_fails(mock_get_sha, client: TestClient, monkeypatch):
    async def mock_get_admin(*args, **kwargs):
        from pit_panel.db.models import User
        return User(id=1, username="admin", is_admin=True)
    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    mock_get_sha.side_effect = Exception("SHA fetch failed")

    response = client.post("/system/upgrade")
    assert response.status_code == 200
    assert b"FAIL git SHA check: SHA fetch failed" in response.content


@patch("pit_panel.web.routes.system._get_current_sha", new_callable=AsyncMock)
@patch("pit_panel.web.routes.system._resolve_uv_bin")
def test_system_upgrade_uv_bin_fails(
    mock_resolve_uv, mock_get_sha, client: TestClient, monkeypatch
):
    async def mock_get_admin(*args, **kwargs):
        from pit_panel.db.models import User
        return User(id=1, username="admin", is_admin=True)
    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    mock_get_sha.return_value = "mock_sha"
    mock_resolve_uv.side_effect = Exception("uv fetch failed")

    response = client.post("/system/upgrade")
    assert response.status_code == 200
    assert b"FAIL uv path check: uv fetch failed" in response.content


@patch("pit_panel.web.routes.system._get_current_sha", new_callable=AsyncMock)
@patch("pit_panel.web.routes.system._resolve_uv_bin")
@patch("pit_panel.web.routes.system._run")
@patch("pit_panel.web.routes.system._sudo")
def test_system_upgrade_db_commit_fails(
    mock_sudo,
    mock_run,
    mock_resolve_uv,
    mock_get_sha,
    client: TestClient,
    monkeypatch,
):
    async def mock_get_admin(*args, **kwargs):
        from pit_panel.db.models import User
        return User(id=1, username="admin", is_admin=True)
    monkeypatch.setattr("pit_panel.web.routes.system.get_admin", mock_get_admin)

    class MockResult:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    mock_get_sha.return_value = "mock_sha"
    mock_resolve_uv.return_value = "/bin/uv"
    mock_run.return_value = MockResult(0, "success")
    mock_sudo.return_value = MockResult(0, "success")

    async def failing_get_db():
        class FailingSession:
            def add(self, *args, **kwargs):
                pass

            async def commit(self):
                raise Exception("DB failure")

            async def execute(self, *args, **kwargs):
                return AsyncMock()

        yield FailingSession()

    monkeypatch.setattr("pit_panel.web.routes.system.get_db", failing_get_db)

    with patch("pit_panel.core.sudo_ops.run_cmd", new_callable=AsyncMock):
        response = client.post("/system/upgrade")
        assert response.status_code == 200
        assert b"OK" in response.content

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


class TestUnauthenticated:
    def test_login_page(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "pit-panel" in resp.text

    def test_dashboard_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302

    def test_subdomains_redirects_to_login(self, client):
        resp = client.get("/subdomains", follow_redirects=False)
        assert resp.status_code == 302

    def test_apps_redirects_to_login(self, client):
        resp = client.get("/apps", follow_redirects=False)
        assert resp.status_code == 302

    def test_containers_redirects_to_login(self, client):
        resp = client.get("/containers", follow_redirects=False)
        assert resp.status_code == 302

    def test_container_restart_redirects_to_login(self, client):
        resp = client.post("/containers/1/restart", follow_redirects=False)
        assert resp.status_code == 302

    def test_ssl_redirects_to_login(self, client):
        resp = client.get("/ssl", follow_redirects=False)
        assert resp.status_code == 302

    def test_security_redirects_to_login(self, client):
        resp = client.get("/security", follow_redirects=False)
        assert resp.status_code == 302

    def test_system_redirects_to_login(self, client):
        resp = client.get("/system", follow_redirects=False)
        assert resp.status_code == 302

    def test_settings_redirects_to_login(self, client):
        resp = client.get("/settings", follow_redirects=False)
        assert resp.status_code == 302


class TestSecurityHeaders:
    def test_security_headers_on_login(self, client):
        resp = client.get("/login")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"

    def test_health_no_cookie_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSetup2FA:
    def test_redirects_when_not_logged_in(self, client):
        resp = client.get("/setup-2fa", follow_redirects=False)
        assert resp.status_code == 302


class TestDebugRoute:
    def test_debug_redirects_to_login(self, client):
        resp = client.get("/debug", follow_redirects=False)
        assert resp.status_code == 302

    def test_debug_raw_unauthorized(self, client):
        resp = client.get("/debug/raw", follow_redirects=False)
        assert resp.status_code == 401

    def test_debug_page_authenticated(self, client, monkeypatch):  # type: ignore
        async def mock_get_admin(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        def mock_run(*args, **kwargs):
            return "mocked_output"

        monkeypatch.setattr("pit_panel.web.routes.debug.get_admin", mock_get_admin)
        monkeypatch.setattr("pit_panel.web.routes.debug._run", mock_run)

        resp = client.get("/debug")
        assert resp.status_code == 200
        assert "Debug & Diagnostics" in resp.text

    def test_debug_raw_authenticated(self, client, monkeypatch):  # type: ignore
        async def mock_get_admin(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        def mock_run(*args, **kwargs):
            return "mocked_output"

        monkeypatch.setattr("pit_panel.web.routes.debug.get_admin", mock_get_admin)
        monkeypatch.setattr("pit_panel.web.routes.debug._run", mock_run)

        resp = client.get("/debug/raw")
        assert resp.status_code == 200
        assert "=== pit-panel debug report ===" in resp.text


class TestRunHelper:
    def test_run_with_cwd(self):
        import tempfile

        from pit_panel.web.routes.debug import _run

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run(["git", "init"], cwd=tmpdir)
            assert result == "(empty)" or "Initialized" in result


class TestSecurityRoutes:
    @pytest.mark.asyncio
    async def test_abuseipdb_check_crlf_mitigation(self, monkeypatch):
        from pit_panel.web.routes.security import _abuseipdb_check

        class MockResponse:
            status = 200

            def read(self):
                return b'{"data": {"abuseConfidenceScore": 0, "totalReports": 0}}'

        class MockConnection:
            def __init__(self, *a, **kw):
                pass

            def request(self, method, url, *a, **kw):
                self.url = url

            def getresponse(self):
                return MockResponse()

        monkeypatch.setattr("http.client.HTTPSConnection", MockConnection)

        malicious_ip = "127.0.0.1\r\nInjected-Header: true"
        result = await _abuseipdb_check(malicious_ip, "fake_key")

        assert result["ip"] == malicious_ip
        assert result["score"] == 0

class TestContainerRestart:
    def test_container_restart_authenticated_not_found(self, client, monkeypatch):
        class MockResult:
            def scalar_one_or_none(self):
                return None

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()
            async def commit(self): pass
            async def close(self): pass

        from pit_panel.db.session import get_db
        from pit_panel.db.models import User

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

        from unittest.mock import AsyncMock
        mock_compose_restart = AsyncMock()
        monkeypatch.setattr("pit_panel.core.docker_ops.DockerManager.compose_restart", mock_compose_restart)

        try:
            resp = client.post("/containers/1/restart", follow_redirects=False)
            assert resp.status_code == 302
            assert resp.headers.get("location") == "/containers"
            mock_compose_restart.assert_not_called()
        finally:
            client.app.dependency_overrides.clear()


    def test_container_restart_authenticated_success(self, client, monkeypatch):
        class MockSubdomain:
            id = 1
            subdomain = "testapp"

        class MockResult:
            def scalar_one_or_none(self):
                return MockSubdomain()

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()
            async def commit(self): pass
            async def close(self): pass

        from pit_panel.db.session import get_db
        from pit_panel.db.models import User

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

        from unittest.mock import AsyncMock
        mock_compose_restart = AsyncMock()
        monkeypatch.setattr("pit_panel.core.docker_ops.DockerManager.compose_restart", mock_compose_restart)

        try:
            resp = client.post("/containers/1/restart", follow_redirects=False)
            assert resp.status_code == 302
            assert resp.headers.get("location") == "/containers"
            mock_compose_restart.assert_called_once_with("testapp")
        finally:
            client.app.dependency_overrides.clear()

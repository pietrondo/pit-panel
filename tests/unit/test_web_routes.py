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
    def test_app_detail_main_domain_display(self, client, monkeypatch):
        from pit_panel.config import Settings
        from pit_panel.db.session import get_db

        settings = Settings(secret_key="test", base_domain="example.com")
        monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: settings)

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

        class MockSD:
            id = 1
            subdomain = "_main_"
            base_domain = "example.com"
            is_main_domain = True
            app_type = "static-nginx"
            last_deployed = None

        class MockResult:
            def scalar_one_or_none(self):
                return MockSD()

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()

            async def close(self):
                pass

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.get("/apps/1", follow_redirects=False)
            assert resp.status_code == 200
            assert "example.com" in resp.text
            assert "Main Domain" in resp.text
        finally:
            client.app.dependency_overrides.clear()

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
                self.headers = kw.get("headers", {})

            def getresponse(self):
                return MockResponse()

        monkeypatch.setattr("http.client.HTTPSConnection", MockConnection)

        # Keep a reference to the latest created connection
        created_connection = None
        original_init = MockConnection.__init__

        def capturing_init(self, *a, **kw):
            nonlocal created_connection
            original_init(self, *a, **kw)
            created_connection = self

        MockConnection.__init__ = capturing_init

        malicious_ip = "127.0.0.1\r\nInjected-Header: true"
        malicious_key = "fake_key\r\nEvil: true"
        result = await _abuseipdb_check(malicious_ip, malicious_key)

        assert "\r" not in created_connection.url
        assert "\n" not in created_connection.url
        assert "127.0.0.1Injected-Header: true" in created_connection.url

        assert "\r" not in created_connection.headers.get("Key", "")
        assert "\n" not in created_connection.headers.get("Key", "")
        assert created_connection.headers.get("Key") == "fake_keyEvil: true"

        assert result["ip"] == "127.0.0.1Injected-Header: true"
        assert result["score"] == 0

    def test_security_overview_authenticated(self, client, monkeypatch):
        from pit_panel.db.models import User

        async def mock_get_admin(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

        async def mock_fw(*args, **kwargs):
            return {"active": True, "rules": []}

        async def mock_f2b(*args, **kwargs):
            return {"active": True, "jails": []}

        monkeypatch.setattr("pit_panel.web.routes.security._firewall_status", mock_fw)
        monkeypatch.setattr("pit_panel.web.routes.security._fail2ban_status", mock_f2b)

        async def mock_get_banned_ips(*args, **kwargs):
            return []

        monkeypatch.setattr("pit_panel.web.routes.security.get_banned_ips", mock_get_banned_ips)

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return []

            def scalar_one_or_none(self):
                return None

            def __iter__(self):
                return iter([])

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()

        async def mock_get_db():
            yield MockSession()

        from pit_panel.web.routes.security import get_db

        client.app.dependency_overrides[get_db] = mock_get_db

        try:
            resp = client.get("/security")
            assert resp.status_code == 200
            assert "<title>pit-panel</title>" in resp.text
            assert "Security" in resp.text
        finally:
            client.app.dependency_overrides.clear()


class TestContainerRestart:
    def test_container_restart_authenticated_not_found(self, client, monkeypatch):
        class MockResult:
            def scalar_one_or_none(self):
                return None

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()

            async def commit(self):
                pass

            async def close(self):
                pass

        from pit_panel.db.models import User
        from pit_panel.db.session import get_db

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

        from unittest.mock import AsyncMock

        mock_compose_restart = AsyncMock()
        monkeypatch.setattr(
            "pit_panel.core.docker_ops.DockerManager.compose_restart", mock_compose_restart
        )

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

            async def commit(self):
                pass

            async def close(self):
                pass

        from pit_panel.db.models import User
        from pit_panel.db.session import get_db

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

        from unittest.mock import AsyncMock

        mock_compose_restart = AsyncMock()
        monkeypatch.setattr(
            "pit_panel.core.docker_ops.DockerManager.compose_restart", mock_compose_restart
        )

        try:
            resp = client.post("/containers/1/restart", follow_redirects=False)
            assert resp.status_code == 302
            assert resp.headers.get("location") == "/containers"
            mock_compose_restart.assert_called_once_with("testapp")
        finally:
            client.app.dependency_overrides.clear()


class TestMainDomain:
    def test_deploy_creates_subdomain_and_route(self, client, monkeypatch):
        from unittest.mock import AsyncMock

        from pit_panel.config import Settings
        from pit_panel.db.session import get_db

        settings = Settings(secret_key="test-secret-key-32chars!!", base_domain="example.com")
        monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: settings)

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

        mock_compose_up = AsyncMock(return_value={"success": True})
        monkeypatch.setattr("pit_panel.core.docker_ops.DockerManager.compose_up", mock_compose_up)

        mock_add_main = AsyncMock(return_value={})
        monkeypatch.setattr("pit_panel.core.caddy.CaddyManager.add_main_domain", mock_add_main)

        class MockResult:
            def scalar_one_or_none(self):
                return None

            def scalars(self):
                return self

            def all(self):
                return []

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()

            async def flush(self):
                pass

            async def commit(self):
                pass

            async def close(self):
                pass

            def add(self, obj):
                pass

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.post(
                "/apps/deploy",
                data={
                    "is_main_domain": "true",
                    "stack_type": "static-nginx",
                    "port": 8082,
                },
                follow_redirects=False,
            )

            assert resp.status_code == 302
            mock_compose_up.assert_called_once_with("_main_")
            mock_add_main.assert_called_once()
        finally:
            client.app.dependency_overrides.clear()

    def test_deploy_twice_rejected(self, client, monkeypatch):
        from pit_panel.config import Settings
        from pit_panel.db.session import get_db

        monkeypatch.setattr(
            "pit_panel.core.app_manager.AppManager.get_template_info", lambda self, t: {"name": t}
        )

        settings = Settings(secret_key="test-secret-key-32chars!!", base_domain="example.com")
        monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: settings)

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

        class MockSD:
            id = 1
            subdomain = "_main_"
            base_domain = "example.com"
            is_main_domain = True
            app_type = "static-nginx"

        class MockResult:
            def scalar_one_or_none(self):
                return MockSD()

            def scalars(self):
                return self

            def all(self):
                return []

        call_count = [0]

        class MockSession:
            async def execute(self, *args, **kwargs):
                call_count[0] += 1
                return MockResult()

            async def close(self):
                pass

            def add(self, obj):
                pass

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.post(
                "/apps/deploy",
                data={
                    "is_main_domain": "true",
                    "stack_type": "static-nginx",
                    "port": 8082,
                },
                follow_redirects=False,
            )

            assert resp.status_code == 200
            assert "Main domain app already deployed" in resp.text
        finally:
            client.app.dependency_overrides.clear()

    def test_main_domain_delete_calls_remove_main_domain(self, client, monkeypatch):
        from unittest.mock import AsyncMock

        from pit_panel.config import Settings
        from pit_panel.db.session import get_db

        settings = Settings(secret_key="test-secret-key-32chars!!", base_domain="example.com")
        monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: settings)

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

        mock_remove = AsyncMock(return_value={})
        monkeypatch.setattr("pit_panel.core.caddy.CaddyManager.remove_main_domain", mock_remove)

        monkeypatch.setattr("pit_panel.core.docker_ops.DockerManager.compose_down", AsyncMock())

        class MockSD:
            id = 1
            subdomain = "_main_"
            base_domain = "example.com"
            is_main_domain = True
            app_type = "static-nginx"

        class MockResult:
            def scalar_one_or_none(self):
                return MockSD()

            def scalars(self):
                return self

            def all(self):
                return []

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()

            async def commit(self):
                pass

            async def close(self):
                pass

            def add(self, obj):
                pass

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.post("/apps/1/delete", follow_redirects=False)
            assert resp.status_code == 302
            mock_remove.assert_called_once_with("example.com")
        finally:
            client.app.dependency_overrides.clear()


class TestContainersRoute:
    def test_containers_list_authenticated_with_data(self, client, monkeypatch):
        from unittest.mock import AsyncMock

        from pit_panel.db.models import Subdomain

        async def mock_get_user(*args, **kwargs):
            from pit_panel.db.models import User

            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

        mock_docker_mgr = AsyncMock()
        mock_docker_mgr.ps_all.return_value = [
            {
                "ID": "123",
                "Names": "test-app",
                "State": "running",
                "Labels": "com.docker.compose.project=app1",
            },
            {"ID": "456", "Names": "orphan-app", "State": "exited", "Labels": ""},
        ]

        monkeypatch.setattr(
            "pit_panel.web.routes.containers.DockerManager", lambda *args: mock_docker_mgr
        )

        class MockResult:
            def scalars(self):
                class MockScalars:
                    def all(self):
                        return [Subdomain(id=1, subdomain="app1", app_type="docker")]

                return MockScalars()

        async def mock_execute(*args, **kwargs):
            return MockResult()

        class MockDb:
            def __init__(self):
                self.execute = mock_execute

        from pit_panel.db.session import get_db

        async def override_get_db():
            yield MockDb()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.get("/containers")
            assert resp.status_code == 200
            assert "test-app" in resp.text
            assert "orphan-app" in resp.text
        finally:
            client.app.dependency_overrides.clear()

    def test_containers_list_unauthenticated(self, client):
        resp = client.get("/containers", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"


class TestSubdomainFiltering:
    def test_subdomains_list_excludes_main_domain(self, client, monkeypatch):
        from pit_panel.db.session import get_db

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

        queried = []

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return []

        class MockSession:
            async def execute(self, query, **kwargs):
                queried.append(str(query))
                return MockResult()

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.get("/subdomains", follow_redirects=False)
            assert resp.status_code == 200
            assert any("is_main_domain" in q for q in queried), (
                f"Expected is_main_domain filter in query, got: {queried}"
            )
        finally:
            client.app.dependency_overrides.clear()

    def test_subdomain_edit_blocks_main_domain(self, client, monkeypatch):
        from pit_panel.db.session import get_db

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

        class MockSD:
            id = 1
            subdomain = "_main_"
            base_domain = "example.com"
            is_main_domain = True

        class MockResult:
            def scalar_one_or_none(self):
                return MockSD()

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.post(
                "/subdomains/1/edit",
                data={"subdomain": "_main_", "app_type": "none"},
                follow_redirects=False,
            )
            assert resp.status_code == 302
            assert resp.headers["location"] == "/subdomains"
        finally:
            client.app.dependency_overrides.clear()

    def test_subdomain_delete_blocks_main_domain(self, client, monkeypatch):
        from pit_panel.db.session import get_db

        async def mock_get_user(*args, **kwargs):
            return User(id=1, username="admin", is_admin=True)

        monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

        class MockSD:
            id = 1
            subdomain = "_main_"
            base_domain = "example.com"
            is_main_domain = True

        class MockResult:
            def scalar_one_or_none(self):
                return MockSD()

        class MockSession:
            async def execute(self, *args, **kwargs):
                return MockResult()

        async def override_get_db():
            yield MockSession()

        client.app.dependency_overrides[get_db] = override_get_db

        try:
            resp = client.post("/subdomains/1/delete", follow_redirects=False)
            assert resp.status_code == 302
            assert resp.headers["location"] == "/subdomains"
        finally:
            client.app.dependency_overrides.clear()

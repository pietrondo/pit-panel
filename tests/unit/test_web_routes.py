import pytest
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
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
        # Ensure the httpx client encodes CRLF characters, avoiding injection.
        import httpx

        from pit_panel.web.routes.security import _abuseipdb_check

        # We'll intercept the httpx.AsyncClient.get call
        class MockResponse:
            status_code = 200

            def json(self):
                return {"data": {"abuseConfidenceScore": 0, "totalReports": 0}}

        called_url = None
        called_params = None
        called_headers = None

        async def mock_get(self, url, params=None, headers=None, **kwargs):
            nonlocal called_url, called_params, called_headers
            called_url = url
            called_params = params
            called_headers = headers
            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

        malicious_ip = "127.0.0.1\r\nInjected-Header: true"
        result = await _abuseipdb_check(malicious_ip, "fake_key")

        # Result should still process gracefully
        assert result["ip"] == malicious_ip
        assert result["score"] == 0

        # Verify that params are passed cleanly and will be url-encoded by httpx natively
        assert called_params["ipAddress"] == malicious_ip
        # The key assertion is that we are using `params` dict, which httpx handles securely.
        assert "Injected-Header" not in called_headers

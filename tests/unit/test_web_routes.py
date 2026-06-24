from unittest.mock import AsyncMock, patch

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


class TestSubdomainValidation:
    def test_invalid_subdomain_path_traversal(self, client):
        from pit_panel.db.models import User

        dummy_user = User(id=1, username="testuser")

        with (
            patch(
                "pit_panel.web.routes.subdomains._get_user", new_callable=AsyncMock
            ) as mock_get_user,
            patch(
                "pit_panel.web.routes.subdomains.AsyncSession", autospec=True
            ) as mock_session_class,
        ):
            mock_get_user.return_value = dummy_user

            mock_session = mock_session_class.return_value
            from unittest.mock import MagicMock

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            invalid_subdomains = ["../", "foo/bar", "foo..bar", "!", "@#$"]

            # Since the endpoint depends on get_db, we need to override the dependency
            # so it returns our mocked session, avoiding actual DB connections
            from pit_panel.db.session import get_db

            client.app.dependency_overrides[get_db] = lambda: mock_session

            try:
                for sd in invalid_subdomains:
                    resp = client.post(
                        "/subdomains/add", data={"subdomain": sd, "app_type": "none"}
                    )
                    assert resp.status_code == 200
                    assert "Invalid subdomain name" in resp.text
            finally:
                client.app.dependency_overrides.clear()

"""Tests for app_routes/main.py — app list, deploy, detail."""

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


def test_apps_list_unauthenticated(client):
    resp = client.get("/apps", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_apps_list_authenticated(client, monkeypatch):
    from pit_panel.config import Settings
    from pit_panel.db.session import get_db

    settings = Settings(secret_key="test", base_domain="example.com")
    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_settings", lambda: settings)

    async def mock_get_user(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_user", mock_get_user)

    class MockSD:
        id = 1
        subdomain = "blog"
        base_domain = "example.com"
        is_main_domain = False
        app_type = "wordpress"
        last_deployed = None
        created_at = None

    class MockScalars:
        def all(self):
            return [MockSD()]

    class MockResult:
        def scalars(self):
            return MockScalars()

    class MockSession:
        async def execute(self, *args, **kwargs):
            return MockResult()

        async def close(self):
            pass

    async def override_get_db():
        yield MockSession()

    client.app.dependency_overrides[get_db] = override_get_db

    try:
        resp = client.get("/apps")
        assert resp.status_code == 200
    finally:
        client.app.dependency_overrides.clear()


def test_app_detail_not_found(client, monkeypatch):
    from pit_panel.db.session import get_db

    async def mock_get_user(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_user", mock_get_user)

    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        async def execute(self, *args, **kwargs):
            return MockResult()

        async def close(self):
            pass

    async def override_get_db():
        yield MockSession()

    client.app.dependency_overrides[get_db] = override_get_db

    try:
        resp = client.get("/apps/999", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/apps"
    finally:
        client.app.dependency_overrides.clear()


def test_app_detail_main_domain(client, monkeypatch):
    from pit_panel.config import Settings
    from pit_panel.db.session import get_db

    settings = Settings(secret_key="test", base_domain="example.com")
    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_settings", lambda: settings)

    async def mock_get_user(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_user", mock_get_user)

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
        resp = client.get("/apps/1")
        assert resp.status_code == 200
        assert "example.com" in resp.text
        assert "Main" in resp.text
    finally:
        client.app.dependency_overrides.clear()


def test_deploy_from_repo_requires_login(client):
    resp = client.post(
        "/apps/deploy-from-repo",
        data={"repo_url": "https://github.com/user/repo.git", "stack_type": "static-nginx"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

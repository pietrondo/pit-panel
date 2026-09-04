from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Site, User
from pit_panel.web.app import create_app
from pit_panel.web.deps import get_admin, get_db


@pytest.fixture
def test_app(monkeypatch, tmp_path):
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

    # Remove middlewares that cause DB access
    app.user_middleware.clear()
    app.middleware_stack = app.build_middleware_stack()
    return app

@pytest.fixture
def client(test_app):
    return TestClient(test_app)

@pytest.fixture
def mock_admin():
    return User(id=1, username="admin")

class MockResult:
    def __init__(self, data):
        self.data = data
    def scalars(self):
        class MockScalars:
            def all(self_inner):
                return self.data
        return MockScalars()

def test_site_builder_create_authenticated_valid(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockResult([])

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites", data={"name": "New Site"}, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"].startswith("/site-builder/sites/")

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

        test_app.dependency_overrides.clear()

def test_site_builder_create_authenticated_invalid_name(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockResult([])

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites", data={"name": " "}, follow_redirects=False)
        assert response.status_code == 200
        assert "Name must be 1-128 characters" in response.text

        test_app.dependency_overrides.clear()

def test_site_builder_edit_unauthenticated(client):
    response = client.get("/site-builder/sites/1/edit", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_site_builder_edit_authenticated_not_found(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/site-builder/sites/1/edit")
        assert response.status_code == 404

        test_app.dependency_overrides.clear()

def test_site_builder_edit_authenticated_wrong_owner(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=2, name="Test Site", status="draft")
    mock_db.get.return_value = mock_site

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/site-builder/sites/1/edit")
        assert response.status_code == 404

        test_app.dependency_overrides.clear()

def test_site_builder_edit_authenticated_valid(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name="Test Site", status="draft")
    mock_db.get.return_value = mock_site

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/site-builder/sites/1/edit")
        assert response.status_code == 200
        assert "Test Site" in response.text or "<!doctype html>" in response.text

        test_app.dependency_overrides.clear()

def test_site_builder_save_widgets_unauthenticated(client):
    response = client.post("/site-builder/sites/1/widgets", json={"tree": {}})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"

def test_site_builder_save_widgets_not_found(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites/1/widgets", json={"tree": {}})
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"

        test_app.dependency_overrides.clear()

def test_site_builder_save_widgets_invalid_json(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name="Test Site")
    mock_db.get.return_value = mock_site

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        # TestClient automatically encodes to json with json kwarg, we need raw data to trigger json parsing error
        response = client.post("/site-builder/sites/1/widgets", content=b"invalid json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_json"

        test_app.dependency_overrides.clear()

def test_site_builder_save_widgets_valid(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name="Test Site")
    mock_db.get.return_value = mock_site

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        payload = {"tree": {"sections": []}}
        response = client.post("/site-builder/sites/1/widgets", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_db.commit.assert_awaited_once()

        test_app.dependency_overrides.clear()

def test_site_builder_publish_unauthenticated(client):
    response = client.post("/site-builder/sites/1/publish")
    assert response.status_code == 401

def test_site_builder_publish_not_found(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites/1/publish")
        assert response.status_code == 404

        test_app.dependency_overrides.clear()

@patch("pit_panel.web.routes.site_builder._published_site_dir")
def test_site_builder_publish_write_failed(mock_pub_dir, test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name="Test Site", subdomain="test", widgets_json={"sections": []})
    mock_db.get.return_value = mock_site

    mock_path = MagicMock()
    mock_path.mkdir.side_effect = OSError("Disk full")
    mock_pub_dir.return_value = mock_path

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites/1/publish")
        assert response.status_code == 500
        assert response.json()["error"] == "write_failed"

        test_app.dependency_overrides.clear()

@patch("pit_panel.web.routes.site_builder._published_site_dir")
@patch("pit_panel.web.routes.site_builder.CaddyManager")
def test_site_builder_publish_success_caddy(mock_caddy_cls, mock_pub_dir, test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name="Test Site", subdomain="test", widgets_json={"sections": []})
    mock_db.get.return_value = mock_site

    mock_path = MagicMock()
    mock_pub_dir.return_value = mock_path
    mock_path.__truediv__.return_value = mock_path # Handle pub_dir / "index.html"

    mock_caddy = AsyncMock()
    mock_caddy_cls.return_value = mock_caddy

    # Monkeypatch settings
    from pit_panel.config import get_settings
    s = get_settings()
    s.base_domain = "example.com"
    s.caddy_admin_url = "http://caddy:2019"

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites/1/publish")
        assert response.status_code == 200
        assert response.json()["status"] == "published"
        assert response.json()["url"] == "https://test.example.com"

        mock_caddy.add_static_subdomain.assert_awaited_once()
        mock_db.commit.assert_awaited_once()

        test_app.dependency_overrides.clear()

@patch("pit_panel.web.routes.site_builder._published_site_dir")
@patch("pit_panel.web.routes.site_builder.CaddyManager")
def test_site_builder_publish_success_no_caddy(mock_caddy_cls, mock_pub_dir, test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name="Test Site", subdomain="test", widgets_json={"sections": []})
    mock_db.get.return_value = mock_site

    mock_path = MagicMock()
    mock_pub_dir.return_value = mock_path
    mock_path.__truediv__.return_value = mock_path

    # Monkeypatch settings
    from pit_panel.config import get_settings
    s = get_settings()
    s.base_domain = None

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites/1/publish")
        assert response.status_code == 200
        assert response.json()["status"] == "published"
        assert response.json()["url"].startswith("file://")

        mock_db.commit.assert_awaited_once()
        mock_caddy_cls.assert_not_called()

        test_app.dependency_overrides.clear()

def test_site_builder_delete_unauthenticated(client):
    response = client.post("/site-builder/sites/1/delete")
    assert response.status_code == 401

def test_site_builder_delete_not_found(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites/1/delete")
        assert response.status_code == 404

        test_app.dependency_overrides.clear()

@patch("pit_panel.web.routes.site_builder._published_site_dir")
@patch("pit_panel.web.routes.site_builder.CaddyManager")
@patch("shutil.rmtree")
def test_site_builder_delete_success(mock_rmtree, mock_caddy_cls, mock_pub_dir, test_app, client, mock_admin, tmp_path):
    mock_db = AsyncMock()

    mock_site = Site(id=1, owner_user_id=1, name="Test Site", subdomain="test", published_html_path=str(tmp_path / "index.html"))
    mock_db.get.return_value = mock_site

    mock_pub_dir.return_value = tmp_path

    mock_caddy = AsyncMock()
    mock_caddy_cls.return_value = mock_caddy

    from pit_panel.config import get_settings
    s = get_settings()
    s.base_domain = "example.com"

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/site-builder"

        mock_rmtree.assert_called_once_with(tmp_path, ignore_errors=True)
        mock_caddy.remove_static_subdomain.assert_awaited_once_with("test", "example.com")

        mock_db.delete.assert_awaited_once_with(mock_site)
        mock_db.commit.assert_awaited_once()

        test_app.dependency_overrides.clear()

def test_site_builder_index_authenticated_with_redirect(test_app, client):
    mock_db = AsyncMock()

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = None

        test_app.dependency_overrides[get_admin] = lambda: None
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/site-builder", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

        test_app.dependency_overrides.clear()

def test_site_builder_create_authenticated_with_redirect(test_app, client):
    mock_db = AsyncMock()

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = None

        test_app.dependency_overrides[get_admin] = lambda: None
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/site-builder/sites", data={"name": "test"}, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

        test_app.dependency_overrides.clear()

def test_site_builder_edit_authenticated_with_redirect(test_app, client):
    mock_db = AsyncMock()

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = None

        test_app.dependency_overrides[get_admin] = lambda: None
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/site-builder/sites/1/edit", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

        test_app.dependency_overrides.clear()
def test_site_builder_index_authenticated_with_sites(test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name="Test Site", updated_at="2023-01-01", status="draft", widgets_json={})
    mock_db.execute.return_value = MockResult([mock_site])

    with patch("pit_panel.web.routes.site_builder.get_admin", new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin

        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/site-builder")
        assert response.status_code == 200

        test_app.dependency_overrides.clear()

@patch('pit_panel.web.routes.site_builder.CaddyManager')
@patch('pit_panel.web.routes.site_builder._published_site_dir')
def test_site_builder_publish_caddy_exception(mock_pub_dir, mock_caddy_cls, test_app, client, mock_admin):
    mock_db = AsyncMock()
    mock_site = Site(id=1, owner_user_id=1, name='Test Site', subdomain='test', widgets_json={'sections': []})
    mock_db.get.return_value = mock_site
    mock_path = MagicMock()
    mock_pub_dir.return_value = mock_path
    mock_path.__truediv__.return_value = mock_path

    from pit_panel.config import get_settings
    s = get_settings()
    s.base_domain = 'example.com'
    s.caddy_admin_url = 'http://caddy:2019'

    mock_caddy = AsyncMock()
    mock_caddy.add_static_subdomain.side_effect = Exception('Caddy failure')
    mock_caddy_cls.return_value = mock_caddy

    with patch('pit_panel.web.routes.site_builder.get_admin', new_callable=AsyncMock) as mock_get_admin:
        mock_get_admin.return_value = mock_admin
        test_app.dependency_overrides[get_admin] = lambda: mock_admin
        test_app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post('/site-builder/sites/1/publish')
        assert response.status_code == 200
        assert 'Caddy route not configured' in response.json()['note']
        test_app.dependency_overrides.clear()

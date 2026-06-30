"""Tests for app_routes/wordpress.py — WP proxy, auto-login, cache/plugin/core."""

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


def test_wp_flush_cache_requires_login(client):
    resp = client.post("/apps/1/wp/flush-cache", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/login"


def test_wp_update_plugins_requires_login(client):
    resp = client.post("/apps/1/wp/update-plugins", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/login"


def test_wp_update_core_requires_login(client):
    resp = client.post("/apps/1/wp/update-core", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/login"


def test_wp_auto_login_requires_login(client):
    resp = client.get("/apps/1/wp-auto-login", follow_redirects=False)
    assert resp.status_code in (302, 307)


def test_wp_proxy_requires_login(client):
    resp = client.get("/apps/1/wp/wp-admin/", follow_redirects=False)
    assert resp.status_code == 401


def test_proxy_service_requires_login(client):
    resp = client.get("/apps/1/proxy/phpmyadmin", follow_redirects=False)
    assert resp.status_code == 401


def test_wp_fix_url_requires_login(client):
    resp = client.post("/apps/1/wp-fix-url", follow_redirects=False)
    assert resp.status_code == 401

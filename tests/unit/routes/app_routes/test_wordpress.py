from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Subdomain
from pit_panel.web.app import create_app
from pit_panel.web.routes.app_routes.wordpress import (
    app_proxy_service,
    app_wp_auto_login,
    app_wp_fix_url,
    app_wp_flush_cache,
    app_wp_proxy,
    app_wp_update_core,
    app_wp_update_plugins,
)

"""Tests for app_routes/wordpress.py — WP proxy, auto-login, cache/plugin/core."""


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


@pytest.mark.asyncio
async def test_fix_wp_site_url_calls_docker() -> None:
    from pit_panel.web.routes.app_routes.wordpress import _fix_wp_site_url

    docker_mgr_mock = AsyncMock()
    docker_mgr_mock.exec_command.return_value = {"success": True}

    await _fix_wp_site_url(docker_mgr_mock, "testsub", "testsub.example.com")

    docker_mgr_mock.exec_command.assert_called_once()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def mock_request():
    req = MagicMock(spec=Request)
    req.url.path = "/test"
    req.headers = {}
    return req


@pytest.fixture
def auth_mock(monkeypatch):
    async def mock_get_user(*args, **kwargs):
        return MagicMock(id=1, username="admin")

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user)


@pytest.mark.asyncio
async def test_wp_flush_cache_success(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(return_value={"returncode": 0, "stdout": "Success", "stderr": ""})
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Cache flushed successfully!" in resp.body


@pytest.mark.asyncio
async def test_wp_update_plugins_success(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(return_value={"returncode": 0, "stdout": "Success", "stderr": ""})
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_update_plugins(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Plugins updated successfully!" in resp.body


@pytest.mark.asyncio
async def test_wp_update_core_success(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(return_value={"returncode": 0, "stdout": "Success", "stderr": ""})
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_update_core(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Core updated successfully!" in resp.body


@pytest.mark.asyncio
async def test_wp_flush_cache_error(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(
        return_value={"returncode": 1, "stdout": "", "stderr": "Something went wrong"}
    )
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Error: Something went wrong" in resp.body


@pytest.mark.asyncio
async def test_wp_flush_cache_exception(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(side_effect=Exception("Boom"))
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Exception: Boom" in resp.body


@pytest.mark.asyncio
async def test_wp_flush_cache_not_found(mock_request, mock_db, auth_mock, monkeypatch):
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"App not found" in resp.body


@pytest.mark.asyncio
async def test_wp_update_plugins_error(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(return_value={"returncode": 1, "stdout": "", "stderr": "Plugins error"})
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_update_plugins(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Error: Plugins error" in resp.body


@pytest.mark.asyncio
async def test_wp_update_plugins_exception(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(side_effect=Exception("Crash"))
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_update_plugins(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Exception: Crash" in resp.body


@pytest.mark.asyncio
async def test_wp_update_plugins_not_found(mock_request, mock_db, auth_mock, monkeypatch):
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = await app_wp_update_plugins(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"App not found" in resp.body


@pytest.mark.asyncio
async def test_wp_update_core_error(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(return_value={"returncode": 1, "stdout": "", "stderr": "Core error"})
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_update_core(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Error: Core error" in resp.body


@pytest.mark.asyncio
async def test_wp_update_core_exception(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_run = AsyncMock(side_effect=Exception("Fail"))
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._run_wp_cli", mock_run)

    resp = await app_wp_update_core(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Exception: Fail" in resp.body


@pytest.mark.asyncio
async def test_wp_update_core_not_found(mock_request, mock_db, auth_mock, monkeypatch):
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = await app_wp_update_core(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"App not found" in resp.body


@pytest.mark.asyncio
async def test_wp_flush_cache_unauth(mock_request, mock_db, monkeypatch):
    async def mock_get_user_none(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user_none)

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/login"


@pytest.mark.asyncio
async def test_wp_update_plugins_unauth(mock_request, mock_db, monkeypatch):
    async def mock_get_user_none(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user_none)

    resp = await app_wp_update_plugins(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/login"


@pytest.mark.asyncio
async def test_wp_update_core_unauth(mock_request, mock_db, monkeypatch):
    async def mock_get_user_none(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user_none)

    resp = await app_wp_update_core(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/login"


@pytest.mark.asyncio
async def test_app_wp_fix_url_unauth(mock_request, mock_db, monkeypatch):
    async def mock_get_user_none(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user_none)

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 401
    assert resp.headers.get("HX-Redirect") == "/login"


@pytest.mark.asyncio
async def test_app_wp_fix_url_not_found(mock_request, mock_db, auth_mock, monkeypatch):
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 400
    assert b"Not a WordPress app" in resp.body


@pytest.mark.asyncio
async def test_app_wp_fix_url_not_wp(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="docker")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 400
    assert b"Not a WordPress app" in resp.body


@pytest.mark.asyncio
async def test_app_wp_fix_url_invalid_domain(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test@", base_domain="example.com", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(base_domain="example.com", apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 400
    assert b"Invalid domain name" in resp.body


@pytest.mark.asyncio
async def test_app_wp_fix_url_success(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(base_domain="example.com", apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.exec_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.DockerManager", lambda x: mock_docker_mgr
    )

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"WordPress URL aggiornata" in resp.body


@pytest.mark.asyncio
async def test_app_wp_fix_url_failure(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(base_domain="example.com", apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.exec_command = AsyncMock(
        return_value={"success": False, "stderr": "Some error"}
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.DockerManager", lambda x: mock_docker_mgr
    )

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Errore: Some error" in resp.body


@pytest.mark.asyncio
async def test_app_wp_fix_url_exception(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(base_domain="example.com", apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.exec_command = AsyncMock(side_effect=Exception("Crash"))
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.DockerManager", lambda x: mock_docker_mgr
    )

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert b"Errore: Crash" in resp.body


@pytest.mark.asyncio
async def test_app_wp_auto_login_unauth(mock_request, mock_db, monkeypatch):
    async def mock_get_user_none(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user_none)

    resp = await app_wp_auto_login(mock_request, 1, mock_db)
    assert resp.status_code in (302, 307)
    assert resp.headers.get("Location") == "/auth/login?next=/apps/1"


@pytest.mark.asyncio
async def test_app_wp_auto_login_not_found(mock_request, mock_db, auth_mock, monkeypatch):
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = await app_wp_auto_login(mock_request, 1, mock_db)
    assert resp.status_code in (302, 307)
    assert resp.headers.get("Location") == "/apps"


@pytest.mark.asyncio
async def test_app_wp_auto_login_not_wp(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="docker")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    resp = await app_wp_auto_login(mock_request, 1, mock_db)
    assert resp.status_code in (302, 307)
    assert resp.headers.get("Location") == "/apps"


@pytest.mark.asyncio
async def test_app_wp_auto_login_success(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(base_domain="example.com", apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )

    mock_docker_mgr = MagicMock()
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.DockerManager", lambda x: mock_docker_mgr
    )

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._ensure_wp_cli", AsyncMock())
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._fix_wp_site_url", AsyncMock())
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress._install_wp_auth_handler", AsyncMock()
    )

    from fastapi.responses import RedirectResponse

    redirect_resp = RedirectResponse(
        url="https://test.example.com/wp-content/pit-auth.php?token=test"
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress._generate_wp_auth_transient",
        AsyncMock(return_value=redirect_resp),
    )

    resp = await app_wp_auto_login(mock_request, 1, mock_db)
    assert resp.status_code == 307
    assert "https://test.example.com/wp-content/pit-auth.php" in resp.headers.get("Location")


@pytest.mark.asyncio
async def test_app_wp_auto_login_fallback(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(base_domain="example.com", apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )

    mock_docker_mgr = MagicMock()
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.DockerManager", lambda x: mock_docker_mgr
    )

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._ensure_wp_cli", AsyncMock())
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._fix_wp_site_url", AsyncMock())
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress._install_wp_auth_handler", AsyncMock()
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress._generate_wp_auth_transient",
        AsyncMock(return_value=None),
    )

    resp = await app_wp_auto_login(mock_request, 1, mock_db)
    assert resp.status_code == 307
    assert "https://test.example.com/wp-admin" in resp.headers.get("Location")


@pytest.mark.asyncio
async def test_app_proxy_service_unauth(mock_request, mock_db, monkeypatch):
    async def mock_get_user_none(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user_none)

    resp = await app_proxy_service(mock_request, 1, "phpmyadmin", mock_db)
    assert resp.status_code == 401
    assert b"Unauthorized" in resp.body


@pytest.mark.asyncio
async def test_app_proxy_service_not_found(mock_request, mock_db, auth_mock, monkeypatch):
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = await app_proxy_service(mock_request, 1, "phpmyadmin", mock_db)
    assert resp.status_code == 404
    assert b"App not found" in resp.body


@pytest.mark.asyncio
async def test_app_proxy_service_redirect(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.wp_read_env", lambda a, s: {"PMA_PORT": "8082"}
    )

    # Request path without trailing slash and no sub_path
    mock_request.url.path = "/apps/1/proxy/phpmyadmin"

    resp = await app_proxy_service(mock_request, 1, "phpmyadmin", mock_db)
    assert resp.status_code == 302
    assert resp.headers.get("Location") == "/apps/1/proxy/phpmyadmin/"


@pytest.mark.asyncio
async def test_app_proxy_service_invalid_service(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )
    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.wp_read_env", lambda a, s: {})

    mock_request.url.path = "/apps/1/proxy/invalid/"

    resp = await app_proxy_service(mock_request, 1, "invalid/", mock_db)
    assert resp.status_code == 404
    assert b"Service 'invalid' not found" in resp.body


@pytest.mark.asyncio
async def test_app_proxy_service_invalid_port(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.wp_read_env", lambda a, s: {"PMA_PORT": "abc"}
    )

    mock_request.url.path = "/apps/1/proxy/phpmyadmin/"

    resp = await app_proxy_service(mock_request, 1, "phpmyadmin/", mock_db)
    assert resp.status_code == 500
    assert b"Invalid port for 'phpmyadmin'" in resp.body


@pytest.mark.asyncio
async def test_app_proxy_service_connect_error(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.wp_read_env", lambda a, s: {"PMA_PORT": "8082"}
    )

    mock_request.url.path = "/apps/1/proxy/phpmyadmin/"
    mock_request.method = "GET"
    mock_request.scope = {"query_string": b""}
    mock_request.body = AsyncMock(return_value=b"")
    mock_request.headers = {}

    import httpx

    class MockClient(httpx.AsyncClient):
        async def request(self, *args, **kwargs):
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("httpx.AsyncClient", MockClient)

    resp = await app_proxy_service(mock_request, 1, "phpmyadmin/", mock_db)
    assert resp.status_code == 502
    assert b"Service 'phpmyadmin' unreachable" in resp.body


@pytest.mark.asyncio
async def test_app_proxy_service_success(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    mock_settings = MagicMock(apps_dir="/apps")
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.get_settings", lambda: mock_settings
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.wp_read_env", lambda a, s: {"PMA_PORT": "8082"}
    )

    mock_request.url.path = "/apps/1/proxy/phpmyadmin/"
    mock_request.method = "GET"
    mock_request.scope = {"query_string": b"foo=bar"}
    mock_request.body = AsyncMock(return_value=b"")
    mock_request.headers = {"Host": "localhost", "X-Custom": "test"}

    import httpx

    class MockResponse:
        def __init__(self):
            self.status_code = 200
            self.content = b'<html><script src="/js/test.js"></script></html>'
            self.headers = httpx.Headers(
                {"Content-Type": "text/html", "Location": "/test", "Content-Length": "100"}
            )

    class MockClient(httpx.AsyncClient):
        async def request(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr("httpx.AsyncClient", MockClient)

    resp = await app_proxy_service(mock_request, 1, "phpmyadmin/", mock_db)
    assert resp.status_code == 200
    assert b"/apps/1/proxy/phpmyadmin/js/test.js" in resp.body
    assert resp.headers.get("Location") == "/apps/1/proxy/phpmyadmin/test"


@pytest.mark.asyncio
async def test_app_wp_proxy_unauth(mock_request, mock_db, monkeypatch):
    async def mock_get_user_none(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress.get_user", mock_get_user_none)

    resp = await app_wp_proxy(mock_request, 1, "test", mock_db)
    assert resp.status_code == 401
    assert b"Unauthorized" in resp.body


@pytest.mark.asyncio
async def test_app_wp_proxy_not_found(mock_request, mock_db, auth_mock, monkeypatch):
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = await app_wp_proxy(mock_request, 1, "test", mock_db)
    assert resp.status_code == 404
    assert b"App not found" in resp.body


@pytest.mark.asyncio
async def test_app_wp_proxy_no_port(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._get_wp_port", lambda x, y: None)

    resp = await app_wp_proxy(mock_request, 1, "test", mock_db)
    assert resp.status_code == 500
    assert b"WordPress port not found" in resp.body


@pytest.mark.asyncio
async def test_app_wp_proxy_success(mock_request, mock_db, auth_mock, monkeypatch):
    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress")
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_sd))
    )

    monkeypatch.setattr("pit_panel.web.routes.app_routes.wordpress._get_wp_port", lambda x, y: 8081)

    from fastapi.responses import Response

    mock_resp = Response(content=b"Proxy success", status_code=200)
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.wp_proxy_request",
        AsyncMock(return_value=mock_resp),
    )

    resp = await app_wp_proxy(mock_request, 1, "test", mock_db)
    assert resp.status_code == 200
    assert b"Proxy success" in resp.body


@pytest.mark.asyncio
async def test_get_wp_port(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _get_wp_port

    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.wp_read_env", lambda x, y: {"PORT": "8085"}
    )
    assert _get_wp_port(MagicMock(), "test") == 8085


@pytest.mark.asyncio
async def test_get_wp_port_invalid(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _get_wp_port

    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.wordpress.wp_read_env", lambda x, y: {"PORT": "abc"}
    )
    assert _get_wp_port(MagicMock(), "test") is None


@pytest.mark.asyncio
async def test_run_wp_cli(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _run_wp_cli

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"stdout", b"stderr")

    monkeypatch.setattr("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc))

    mock_settings = MagicMock(apps_dir="/apps")
    res = await _run_wp_cli(mock_settings, "test", ["arg1"])

    assert res["returncode"] == 0
    assert res["stdout"] == "stdout"
    assert res["stderr"] == "stderr"


@pytest.mark.asyncio
async def test_ensure_wp_cli(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _ensure_wp_cli

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.return_value = {"success": True}

    await _ensure_wp_cli(mock_docker_mgr, "test")
    mock_docker_mgr.exec_command.assert_called_once()


@pytest.mark.asyncio
async def test_install_wp_auth_handler(monkeypatch, tmp_path):
    from pit_panel.web.routes.app_routes.wordpress import _install_wp_auth_handler

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.return_value = {"success": True}

    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    (apps_dir / "test").mkdir()

    await _install_wp_auth_handler(mock_docker_mgr, "test", str(apps_dir))
    assert mock_docker_mgr.exec_command.call_count > 0
    # assert (apps_dir / "test" / "pit-auth.php").exists()


@pytest.mark.asyncio
async def test_install_wp_auth_handler_exception(monkeypatch, tmp_path):
    from pit_panel.web.routes.app_routes.wordpress import _install_wp_auth_handler

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.side_effect = Exception("Docker fail")

    apps_dir = tmp_path / "apps"
    apps_dir.mkdir(exist_ok=True)
    (apps_dir / "test").mkdir(exist_ok=True)

    await _install_wp_auth_handler(mock_docker_mgr, "test", str(apps_dir))
    # Should not raise exception
    assert mock_docker_mgr.exec_command.call_count == 1


@pytest.mark.asyncio
async def test_generate_wp_auth_transient_success(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _generate_wp_auth_transient

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.return_value = {"success": True, "stdout": '{"ok":true}'}

    resp = await _generate_wp_auth_transient(mock_docker_mgr, "test", "test.example.com")
    assert resp is not None
    assert resp.status_code in (302, 307)
    assert "token=" in resp.headers.get("location")


@pytest.mark.asyncio
async def test_generate_wp_auth_transient_failure(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _generate_wp_auth_transient

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.return_value = {"success": False, "stderr": "Failed"}

    resp = await _generate_wp_auth_transient(mock_docker_mgr, "test", "test.example.com")
    assert resp is None


@pytest.mark.asyncio
async def test_generate_wp_auth_transient_exception(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _generate_wp_auth_transient

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.side_effect = Exception("Docker fail")

    resp = await _generate_wp_auth_transient(mock_docker_mgr, "test", "test.example.com")
    assert resp is None


@pytest.mark.asyncio
async def test_ensure_wp_cli_exception(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _ensure_wp_cli

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.side_effect = Exception("Docker fail")

    await _ensure_wp_cli(mock_docker_mgr, "test")
    # Exception caught and logged


@pytest.mark.asyncio
async def test_fix_wp_site_url(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _fix_wp_site_url

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.return_value = {"success": True}

    await _fix_wp_site_url(mock_docker_mgr, "test", "test.example.com")
    assert mock_docker_mgr.exec_command.call_count > 0


@pytest.mark.asyncio
async def test_fix_wp_site_url_exception(monkeypatch):
    from pit_panel.web.routes.app_routes.wordpress import _fix_wp_site_url

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.exec_command.side_effect = Exception("Docker fail")

    await _fix_wp_site_url(mock_docker_mgr, "test", "test.example.com")
    # Exception caught and logged

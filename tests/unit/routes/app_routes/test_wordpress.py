"""Tests for app_routes/wordpress.py — WP proxy, auto-login, cache/plugin/core."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Subdomain
from pit_panel.web.app import create_app
from pit_panel.web.routes.app_routes.wordpress import (
    _ensure_wp_cli,
    _generate_wp_auth_transient,
    _install_wp_auth_handler,
    app_proxy_service,
    app_wp_auto_login,
    app_wp_fix_url,
    app_wp_flush_cache,
    app_wp_proxy,
    app_wp_update_core,
    app_wp_update_plugins,
)


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
def mock_request():
    req = MagicMock(spec=Request)
    req.headers = {}
    return req


@pytest.fixture
def mock_db():
    db = AsyncMock()
    mock_result = MagicMock()

    mock_sd = Subdomain(id=1, subdomain="test", app_type="wordpress", base_domain="example.com")
    mock_result.scalar_one_or_none.return_value = mock_sd
    db.execute.return_value = mock_result

    return db


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress._run_wp_cli")
async def test_app_wp_flush_cache(
    mock_run_cli, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_run_cli.return_value = {"returncode": 0, "stdout": "Success", "stderr": ""}

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "successfully" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress._run_wp_cli")
async def test_app_wp_flush_cache_error(
    mock_run_cli, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_run_cli.return_value = {"returncode": 1, "stdout": "", "stderr": "Error"}

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "Error" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress._run_wp_cli")
async def test_app_wp_flush_cache_exception(
    mock_run_cli, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_run_cli.side_effect = Exception("Test exception")

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "Exception" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
async def test_app_wp_flush_cache_not_found(mock_get_user, mock_request, mock_db):
    mock_get_user.return_value = {"id": 1}
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    resp = await app_wp_flush_cache(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "App not found" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress._run_wp_cli")
async def test_app_wp_update_plugins(
    mock_run_cli, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_run_cli.return_value = {"returncode": 0, "stdout": "Success", "stderr": ""}

    resp = await app_wp_update_plugins(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "successfully" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress._run_wp_cli")
async def test_app_wp_update_core(
    mock_run_cli, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_run_cli.return_value = {"returncode": 0, "stdout": "Success", "stderr": ""}

    resp = await app_wp_update_core(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "successfully" in resp.body.decode()


@pytest.mark.asyncio
async def test_ensure_wp_cli():
    docker_mgr = AsyncMock()
    await _ensure_wp_cli(docker_mgr, "test")
    docker_mgr.exec_command.assert_called_once()
    assert "test -f /tmp/wp-cli.phar" in docker_mgr.exec_command.call_args[0][2][2]


@pytest.mark.asyncio
async def test_install_wp_auth_handler(tmp_path):
    docker_mgr = AsyncMock()
    apps_dir = tmp_path / "apps"
    sd_dir = apps_dir / "test"
    sd_dir.mkdir(parents=True)

    await _install_wp_auth_handler(docker_mgr, "test", str(apps_dir))
    assert docker_mgr.exec_command.call_count == 2
    assert (sd_dir / ".pit-auth-handler.php").exists()


@pytest.mark.asyncio
async def test_install_wp_auth_handler_exists(tmp_path):
    docker_mgr = AsyncMock()
    apps_dir = tmp_path / "apps"
    sd_dir = apps_dir / "test"
    sd_dir.mkdir(parents=True)
    (sd_dir / ".pit-auth-handler.php").write_text("exists")

    await _install_wp_auth_handler(docker_mgr, "test", str(apps_dir))
    assert docker_mgr.exec_command.call_count == 0


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.os.urandom")
async def test_generate_wp_auth_transient(mock_urandom):
    mock_urandom.return_value = b"123456789012"
    docker_mgr = AsyncMock()
    docker_mgr.exec_command.return_value = {"success": True}

    resp = await _generate_wp_auth_transient(docker_mgr, "test", "example.com")
    assert resp is not None
    assert resp.status_code == 307
    assert "example.com/wp-content/pit-auth.php" in resp.headers["location"]


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.os.urandom")
async def test_generate_wp_auth_transient_fail(mock_urandom):
    mock_urandom.return_value = b"123456789012"
    docker_mgr = AsyncMock()
    docker_mgr.exec_command.return_value = {"success": False, "stderr": "error"}

    resp = await _generate_wp_auth_transient(docker_mgr, "test", "example.com")
    assert resp is None


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress.DockerManager")
@patch("pit_panel.web.routes.app_routes.wordpress._ensure_wp_cli")
@patch("pit_panel.web.routes.app_routes.wordpress._fix_wp_site_url")
@patch("pit_panel.web.routes.app_routes.wordpress._install_wp_auth_handler")
@patch("pit_panel.web.routes.app_routes.wordpress._generate_wp_auth_transient")
async def test_app_wp_auto_login(
    mock_gen_transient,
    mock_inst_handler,
    mock_fix_url,
    mock_ensure_cli,
    mock_docker_mgr,
    mock_get_settings,
    mock_get_user,
    mock_request,
    mock_db,
):
    mock_get_user.return_value = {"id": 1}
    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.apps_dir = "/apps"
    mock_get_settings.return_value = mock_settings

    mock_resp = RedirectResponse(url="http://test")
    mock_gen_transient.return_value = mock_resp

    resp = await app_wp_auto_login(mock_request, 1, mock_db)
    assert resp is mock_resp


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress.DockerManager")
@patch("pit_panel.web.routes.app_routes.wordpress._ensure_wp_cli")
@patch("pit_panel.web.routes.app_routes.wordpress._fix_wp_site_url")
@patch("pit_panel.web.routes.app_routes.wordpress._install_wp_auth_handler")
@patch("pit_panel.web.routes.app_routes.wordpress._generate_wp_auth_transient")
async def test_app_wp_auto_login_fallback(
    mock_gen_transient,
    mock_inst_handler,
    mock_fix_url,
    mock_ensure_cli,
    mock_docker_mgr,
    mock_get_settings,
    mock_get_user,
    mock_request,
    mock_db,
):
    mock_get_user.return_value = {"id": 1}
    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.apps_dir = "/apps"
    mock_get_settings.return_value = mock_settings

    mock_gen_transient.return_value = None

    resp = await app_wp_auto_login(mock_request, 1, mock_db)
    assert resp.status_code == 307
    assert "https://test.example.com/wp-admin" in resp.headers["location"]


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress.DockerManager")
async def test_app_wp_fix_url(
    mock_docker_mgr, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.apps_dir = "/apps"
    mock_get_settings.return_value = mock_settings

    mock_mgr_instance = AsyncMock()
    mock_mgr_instance.exec_command.side_effect = [
        {"success": True, "stdout": "", "stderr": ""},
        {"success": True, "stdout": "", "stderr": ""},
    ]
    mock_docker_mgr.return_value = mock_mgr_instance

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "aggiornata" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress.DockerManager")
async def test_app_wp_fix_url_error(
    mock_docker_mgr, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.apps_dir = "/apps"
    mock_get_settings.return_value = mock_settings

    mock_mgr_instance = AsyncMock()
    mock_mgr_instance.exec_command.side_effect = [
        {"success": True, "stdout": "", "stderr": ""},
        {"success": False, "stdout": "", "stderr": "error"},
    ]
    mock_docker_mgr.return_value = mock_mgr_instance

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "Errore" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress.DockerManager")
async def test_app_wp_fix_url_exception(
    mock_docker_mgr, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.apps_dir = "/apps"
    mock_get_settings.return_value = mock_settings

    mock_mgr_instance = AsyncMock()
    mock_mgr_instance.exec_command.side_effect = Exception("error")
    mock_docker_mgr.return_value = mock_mgr_instance

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 200
    assert "Errore" in resp.body.decode()
    assert "error" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
async def test_app_wp_fix_url_invalid_domain(mock_get_user, mock_request, mock_db):
    mock_get_user.return_value = {"id": 1}
    mock_sd = Subdomain(id=1, subdomain="test@", app_type="wordpress", base_domain="example.com")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_sd
    mock_db.execute.return_value = mock_result

    resp = await app_wp_fix_url(mock_request, 1, mock_db)
    assert resp.status_code == 400
    assert "Invalid domain name" in resp.body.decode()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress.wp_read_env")
@patch("httpx.AsyncClient")
async def test_app_proxy_service(
    mock_async_client, mock_read_env, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_settings = MagicMock()
    mock_get_settings.return_value = mock_settings
    mock_read_env.return_value = {"PMA_PORT": "8082"}

    mock_request.url.path = "/apps/1/proxy/phpmyadmin/test"
    mock_request.method = "GET"
    mock_request.scope = {}
    mock_request.body = AsyncMock(return_value=b"")
    mock_request.headers = {"host": "localhost"}

    mock_client_instance = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.content = b'<html><a href="/test">link</a><script src="/js/test.js"></script></html>'
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.status_code = 200
    mock_client_instance.request.return_value = mock_resp

    mock_async_client.return_value.__aenter__.return_value = mock_client_instance

    resp = await app_proxy_service(mock_request, 1, "phpmyadmin/test", mock_db)
    assert resp.status_code == 200
    assert b"/apps/1/proxy/phpmyadmin/js/" in resp.body


@pytest.mark.asyncio
@patch("pit_panel.web.routes.app_routes.wordpress.get_user")
@patch("pit_panel.web.routes.app_routes.wordpress.get_settings")
@patch("pit_panel.web.routes.app_routes.wordpress._get_wp_port")
@patch("pit_panel.web.routes.app_routes.wordpress.wp_proxy_request")
async def test_app_wp_proxy(
    mock_proxy_req, mock_get_port, mock_get_settings, mock_get_user, mock_request, mock_db
):
    mock_get_user.return_value = {"id": 1}
    mock_settings = MagicMock()
    mock_get_settings.return_value = mock_settings
    mock_get_port.return_value = 8080

    mock_resp = Response(content="success", status_code=200)
    mock_proxy_req.return_value = mock_resp

    resp = await app_wp_proxy(mock_request, 1, "test", mock_db)
    assert resp is mock_resp
    mock_proxy_req.assert_called_once_with(mock_request, 8080, 1)

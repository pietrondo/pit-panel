import subprocess
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from pit_panel.db.models import User
from pit_panel.web.routes.ssl import (
    CaddyfileConfig,
    SSLGenerateForm,
    _check_caddy_running,
    _check_port80,
    _generate_caddyfile,
    ssl_generate,
    ssl_renew,
    ssl_setup,
)


@pytest.mark.asyncio
async def test_ssl_setup_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    response = await ssl_setup(mock_request, mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_ssl_setup_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.caddy_admin_url = "http://caddy:2019"
    monkeypatch.setattr("pit_panel.web.routes.ssl.get_settings", lambda: mock_settings)

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.get_certificates = AsyncMock(return_value=[])
    monkeypatch.setattr("pit_panel.web.routes.ssl.CaddyManager", mock_caddy_manager)

    monkeypatch.setattr("pit_panel.web.routes.ssl._check_caddy_running", lambda: True)
    monkeypatch.setattr("pit_panel.web.routes.ssl._check_port80", lambda: True)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.ssl.render", mock_render)

    class MockPath:
        def __init__(self, *args):
            pass

        def exists(self):
            return True

        def read_text(self):
            return "existing caddyfile"

    monkeypatch.setattr("pit_panel.web.routes.ssl.Path", MockPath)

    await ssl_setup(mock_request, mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["user"] == user
    assert kwargs["caddy_running"] is True
    assert kwargs["port80_free"] is True
    assert kwargs["current_caddyfile"] == "existing caddyfile"


@pytest.mark.asyncio
async def test_ssl_generate_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    form = SSLGenerateForm()

    response = await ssl_generate(mock_request, form=form, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_ssl_generate_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.effective_domain = "example.com"
    mock_settings.panel_subdomain = "panel"
    monkeypatch.setattr("pit_panel.web.routes.ssl.get_settings", lambda: mock_settings)

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.generate_and_reload = AsyncMock(return_value="Reloaded")
    mock_caddy_manager.return_value.save_api_token = MagicMock(return_value=" Saved Token")
    mock_caddy_manager.return_value.get_certificates = AsyncMock(return_value=[])
    monkeypatch.setattr("pit_panel.web.routes.ssl.CaddyManager", mock_caddy_manager)

    monkeypatch.setattr("pit_panel.web.routes.ssl._check_caddy_running", lambda: True)
    monkeypatch.setattr("pit_panel.web.routes.ssl._check_port80", lambda: True)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.ssl.render", mock_render)

    form = SSLGenerateForm.as_form(
        email="admin@example.com",
        dns_provider="cloudflare",
        api_token="secret",
        api_var="CF_TOKEN",
        acme_provider="letsencrypt",
        eab_key_id="",
        eab_hmac="",
    )

    await ssl_generate(mock_request, form=form, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["caddy_result"] == "Reloaded Saved Token"


@pytest.mark.asyncio
async def test_ssl_renew_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    response = await ssl_renew(mock_request, domain="example.com", db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_ssl_renew_invalid_domain(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    response = await ssl_renew(mock_request, domain="invalid domain!", db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ssl_renew_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.ssl.get_settings", lambda: mock_settings)

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.renew_certificate = AsyncMock(return_value="Renewed")
    mock_caddy_manager.return_value.get_certificates = AsyncMock(return_value=[])
    monkeypatch.setattr("pit_panel.web.routes.ssl.CaddyManager", mock_caddy_manager)

    monkeypatch.setattr("pit_panel.web.routes.ssl._check_caddy_running", lambda: True)
    monkeypatch.setattr("pit_panel.web.routes.ssl._check_port80", lambda: True)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.ssl.render", mock_render)

    class MockPath:
        def __init__(self, *args):
            pass

        def exists(self):
            return True

        def read_text(self):
            return "existing caddyfile"

    monkeypatch.setattr("pit_panel.web.routes.ssl.Path", MockPath)

    await ssl_renew(mock_request, domain="example.com", db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["renew_result"] == "Renewed"


def test_check_caddy_running(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_result)
    assert _check_caddy_running() is True

    mock_result.returncode = 1
    assert _check_caddy_running() is False

    monkeypatch.setattr(subprocess, "run", MagicMock(side_effect=Exception("Error")))
    assert _check_caddy_running() is False


def test_check_port80(monkeypatch):
    import socket

    class MockSocket:
        def __init__(self, *args):
            pass

        def setsockopt(self, *args):
            pass

        def settimeout(self, *args):
            pass

        def bind(self, *args):
            pass

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", lambda *args: MockSocket())
    assert _check_port80() is True

    class ErrorSocket:
        def __init__(self, *args):
            pass

        def setsockopt(self, *args):
            pass

        def settimeout(self, *args):
            pass

        def bind(self, *args):
            raise OSError("Port in use")

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", lambda *args: ErrorSocket())
    assert _check_port80() is False


@pytest.mark.asyncio
async def test_ssl_generate_authenticated_no_dns(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.ssl.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.effective_domain = "example.com"
    mock_settings.panel_subdomain = "panel"
    monkeypatch.setattr("pit_panel.web.routes.ssl.get_settings", lambda: mock_settings)

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.generate_and_reload = AsyncMock(return_value="Reloaded")
    mock_caddy_manager.return_value.save_api_token = MagicMock(return_value=" Saved Token")
    mock_caddy_manager.return_value.get_certificates = AsyncMock(return_value=[])
    monkeypatch.setattr("pit_panel.web.routes.ssl.CaddyManager", mock_caddy_manager)

    monkeypatch.setattr("pit_panel.web.routes.ssl._check_caddy_running", lambda: True)
    monkeypatch.setattr("pit_panel.web.routes.ssl._check_port80", lambda: True)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.ssl.render", mock_render)

    form = SSLGenerateForm.as_form(
        email="admin@example.com",
        dns_provider="",
        api_token="",
        api_var="CF_TOKEN",
        acme_provider="letsencrypt",
        eab_key_id="",
        eab_hmac="",
    )

    await ssl_generate(mock_request, form=form, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["caddy_result"] == "Reloaded"


def test_generate_caddyfile_acme_providers():
    config = CaddyfileConfig(
        email="test@test.com",
        domain="example.com",
        panel_sub="panel",
        acme_provider="zerossl",
        eab_key_id="key123",
        eab_hmac="hmac456",
        dns_provider="cloudflare",
    )
    res = _generate_caddyfile(config)
    assert 'zerossl {eab "key123" "hmac456"}' in res

    config.acme_provider = "buypass"
    res = _generate_caddyfile(config)
    assert "issuer buypass" in res

    config.acme_provider = "google"
    res = _generate_caddyfile(config)
    assert 'google {eab "key123" "hmac456"}' in res


def test_generate_caddyfile_no_dns_zerossl():
    config = CaddyfileConfig(
        email="test@test.com",
        domain="example.com",
        panel_sub="panel",
        acme_provider="zerossl",
        eab_key_id="key123",
        eab_hmac="hmac456",
        dns_provider="",
    )
    res = _generate_caddyfile(config)
    assert 'zerossl {eab "key123" "hmac456"}' in res
    assert "reverse_proxy 127.0.0.1:8080" in res


def test_sanitize_none():
    from pit_panel.web.routes.ssl import _sanitize

    assert _sanitize(None) == ""


def test_generate_caddyfile_unknown_acme_provider():
    config = CaddyfileConfig(
        email="test@test.com",
        domain="example.com",
        panel_sub="panel",
        acme_provider="unknown",
        dns_provider="",
    )
    res = _generate_caddyfile(config)
    assert "panel.example.com {\n    reverse_proxy 127.0.0.1:8080\n}" in res


def test_get_tls_block_no_parts():
    from pit_panel.web.routes.ssl import _get_tls_block

    res = _get_tls_block("", "", "")
    assert res == ""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from pit_panel.db.models import Subdomain, User
from pit_panel.web.routes.subdomains import (
    _log_audit,
    subdomain_add,
    subdomain_delete,
    subdomain_edit,
    subdomains_list,
)


@pytest.mark.asyncio
async def test_subdomains_list_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    response = await subdomains_list(mock_request, mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_subdomains_list_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")
    subdomain = Subdomain(id=1, subdomain="test", base_domain="example.com")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.render", mock_render)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [subdomain]
    mock_db.execute.return_value = mock_result

    await subdomains_list(mock_request, mock_db)

    mock_render.assert_called_once_with(
        "subdomains.html", user=user, subdomains=[subdomain], error=None
    )


@pytest.mark.asyncio
async def test_subdomain_add_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    response = await subdomain_add(mock_request, subdomain="test", db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_subdomain_add_invalid_name(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.render", mock_render)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    await subdomain_add(mock_request, subdomain="invalid name!", db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["error"] == "Invalid subdomain name"


@pytest.mark.asyncio
async def test_subdomain_add_exists(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.render", mock_render)

    mock_result_existing = MagicMock()
    mock_result_existing.scalar_one_or_none.return_value = Subdomain(id=1)

    mock_result_all = MagicMock()
    mock_result_all.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result_existing, mock_result_all]

    await subdomain_add(mock_request, subdomain="test", db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["error"] == "Subdomain already exists"


@pytest.mark.asyncio
async def test_subdomain_add_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.caddy_admin_url = "http://caddy:2019"
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    mock_result_existing = MagicMock()
    mock_result_existing.scalar_one_or_none.return_value = None

    mock_db.execute.return_value = mock_result_existing

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.CaddyManager", mock_caddy_manager)

    response = await subdomain_add(mock_request, subdomain="newsub", app_type="custom", db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_db.add.assert_called()
    assert mock_db.commit.call_count == 2
    mock_caddy_manager.return_value.add_subdomain.assert_called_once_with("newsub", "example.com")


@pytest.mark.asyncio
async def test_subdomain_add_caddy_error(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.caddy_admin_url = "http://caddy:2019"
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    mock_result_existing = MagicMock()
    mock_result_existing.scalar_one_or_none.return_value = None

    mock_db.execute.return_value = mock_result_existing

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.add_subdomain = AsyncMock(side_effect=Exception("Caddy failed"))
    monkeypatch.setattr("pit_panel.web.routes.subdomains.CaddyManager", mock_caddy_manager)

    response = await subdomain_add(mock_request, subdomain="newsub", db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_subdomain_edit_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    response = await subdomain_edit(
        mock_request, sd_id=1, subdomain="test", app_type="none", db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_subdomain_edit_not_found_or_main(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    # Test not found
    mock_result_none = MagicMock()
    mock_result_none.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_none

    response = await subdomain_edit(
        mock_request, sd_id=1, subdomain="test", app_type="none", db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    # Test main domain
    main_sd = Subdomain(id=1, is_main_domain=True)
    mock_result_main = MagicMock()
    mock_result_main.scalar_one_or_none.return_value = main_sd
    mock_db.execute.return_value = mock_result_main

    response2 = await subdomain_edit(
        mock_request, sd_id=1, subdomain="test", app_type="none", db=mock_db
    )

    assert isinstance(response2, RedirectResponse)
    assert response2.status_code == 302


@pytest.mark.asyncio
async def test_subdomain_edit_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    sd = Subdomain(id=1, subdomain="oldsub", app_type="oldtype", is_main_domain=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.remove_subdomain = AsyncMock()
    mock_caddy_manager.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.CaddyManager", mock_caddy_manager)

    response = await subdomain_edit(
        mock_request, sd_id=1, subdomain="newsub", app_type="newtype", db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    assert sd.subdomain == "newsub"
    assert sd.app_type == "newtype"

    mock_caddy_manager.return_value.remove_subdomain.assert_called_once_with(
        "oldsub", "example.com"
    )
    mock_caddy_manager.return_value.add_subdomain.assert_called_once_with("newsub", "example.com")


@pytest.mark.asyncio
async def test_subdomain_edit_invalid_name(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    sd = Subdomain(id=1, subdomain="oldsub", app_type="oldtype", is_main_domain=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    response = await subdomain_edit(
        mock_request, sd_id=1, subdomain="invalid name!", app_type="newtype", db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    assert sd.subdomain == "oldsub"  # Name shouldn't change
    assert sd.app_type == "newtype"  # But app type should


@pytest.mark.asyncio
async def test_subdomain_edit_caddy_error(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    sd = Subdomain(id=1, subdomain="oldsub", app_type="oldtype", is_main_domain=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.remove_subdomain = AsyncMock(
        side_effect=Exception("Caddy failed")
    )
    monkeypatch.setattr("pit_panel.web.routes.subdomains.CaddyManager", mock_caddy_manager)

    response = await subdomain_edit(
        mock_request, sd_id=1, subdomain="newsub", app_type="newtype", db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_subdomain_delete_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    response = await subdomain_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_subdomain_delete_not_found_or_main(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    # Test not found
    mock_result_none = MagicMock()
    mock_result_none.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_none

    response = await subdomain_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    # Test main domain
    main_sd = Subdomain(id=1, is_main_domain=True)
    mock_result_main = MagicMock()
    mock_result_main.scalar_one_or_none.return_value = main_sd
    mock_db.execute.return_value = mock_result_main

    response2 = await subdomain_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response2, RedirectResponse)
    assert response2.status_code == 302


@pytest.mark.asyncio
async def test_subdomain_delete_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    sd = Subdomain(id=1, subdomain="testsub", is_main_domain=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.remove_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.subdomains.CaddyManager", mock_caddy_manager)

    response = await subdomain_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_caddy_manager.return_value.remove_subdomain.assert_called_once_with(
        "testsub", "example.com"
    )
    mock_db.delete.assert_called_once_with(sd)


@pytest.mark.asyncio
async def test_subdomain_delete_caddy_error(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="testuser")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_settings", lambda: mock_settings)

    sd = Subdomain(id=1, subdomain="testsub", is_main_domain=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_caddy_manager = MagicMock()
    mock_caddy_manager.return_value.remove_subdomain = AsyncMock(
        side_effect=Exception("Caddy failed")
    )
    monkeypatch.setattr("pit_panel.web.routes.subdomains.CaddyManager", mock_caddy_manager)

    response = await subdomain_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    mock_db.delete.assert_called_once_with(sd)


@pytest.mark.asyncio
async def test_log_audit_no_client():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_request = MagicMock(spec=Request)
    mock_request.client = None
    mock_request.headers.get.return_value = "TestAgent"

    await _log_audit(mock_db, 1, "action", "target", 1, {"key": "val"}, mock_request)

    mock_db.add.assert_called_once()
    added_entry = mock_db.add.call_args[0][0]
    assert added_entry.ip is None

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from pit_panel.db.models import AuditLog, User
from pit_panel.web.routes.settings import settings_page


@pytest.mark.asyncio
async def test_settings_page_unauthenticated(monkeypatch):
    # Setup mocks
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    # Call function
    response = await settings_page(mock_request, mock_db)

    # Assert
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_settings_page_authenticated(monkeypatch):
    # Setup mocks
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    # Mock render
    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.render", mock_render)

    # Mock settings
    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.get_settings", lambda: mock_settings)

    # Mock DB execute for audit entries
    mock_result = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result.scalars.return_value.all.return_value = [mock_audit]
    mock_db.execute.return_value = mock_result

    # Call function
    await settings_page(mock_request, mock_db)

    # Assert
    mock_render.assert_called_once_with(
        "settings.html",
        user=user,
        audit_entries=[mock_audit],
        settings=mock_settings,
        config_saved=False,
        error=None,
    )
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_settings_update_unauthenticated(monkeypatch):
    # Setup mocks
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    # Call function
    from pit_panel.web.routes.settings import settings_update

    response = await settings_update(
        mock_request,
        base_domain="",
        panel_subdomain="panel",
        abuseipdb_api_key="",
        sudo_password="",
        telegram_bot_token="",
        telegram_chat_id="",
        db=mock_db,
    )

    # Assert
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_settings_update_existing_settings(monkeypatch):
    # Setup mocks
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    # Mock DB select for SystemSettings
    mock_row_base = MagicMock()
    mock_row_panel = MagicMock()
    mock_row_host = MagicMock()
    mock_row_abuseipdb = MagicMock()
    mock_row_sudo = MagicMock()

    # Mock row setup
    mock_row_base.key = "base_domain"
    mock_row_panel.key = "panel_subdomain"
    mock_row_host.key = "host"
    mock_row_abuseipdb.key = "abuseipdb_api_key"
    mock_row_sudo.key = "sudo_password"
    mock_row_telegram_token = MagicMock()
    mock_row_telegram_token.key = "telegram_bot_token"
    mock_row_telegram_chat = MagicMock()
    mock_row_telegram_chat.key = "telegram_chat_id"

    mock_result_settings = MagicMock()
    mock_result_settings.scalars.return_value.all.return_value = [
        mock_row_base,
        mock_row_panel,
        mock_row_host,
        mock_row_abuseipdb,
        mock_row_sudo,
        mock_row_telegram_token,
        mock_row_telegram_chat,
    ]

    # Mock DB select for AuditLog
    mock_result_audit = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result_audit.scalars.return_value.all.return_value = [mock_audit]

    # Route calls db.execute 1 time for settings IN query + 1 time for audit = 2 calls
    mock_db.execute.side_effect = [
        mock_result_settings,
        mock_result_audit,
    ]

    # Mock settings
    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.get_settings", lambda: mock_settings)

    # Mock render
    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.render", mock_render)

    # Call function
    from pit_panel.web.routes.settings import settings_update

    await settings_update(
        mock_request,
        base_domain=" newdomain.com ",
        panel_subdomain=" newpanel ",
        abuseipdb_api_key="",
        sudo_password="",
        telegram_bot_token="",
        telegram_chat_id="",
        db=mock_db,
    )

    # Assert SystemSettings were updated
    assert mock_row_base.value == {"v": "newdomain.com"}
    assert mock_row_base.updated_by == user.id
    assert mock_row_panel.value == {"v": "newpanel"}
    assert mock_row_panel.updated_by == user.id
    assert mock_row_host.value == {"v": "127.0.0.1"}
    assert mock_row_host.updated_by == user.id

    # Assert no new settings added (all rows already exist)
    mock_db.add.assert_not_called()

    # Assert commit called
    mock_db.commit.assert_awaited_once()

    # Assert in-memory settings were updated
    assert mock_settings.base_domain == "newdomain.com"
    assert mock_settings.panel_subdomain == "newpanel"
    assert mock_settings.host == "127.0.0.1"

    # Assert render called
    mock_render.assert_called_once_with(
        "settings.html",
        user=user,
        audit_entries=[mock_audit],
        settings=mock_settings,
        config_saved=True,
        error=None,
    )


@pytest.mark.asyncio
async def test_settings_update_new_settings(monkeypatch):
    # Setup mocks
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    # Mock DB select for SystemSettings (returns empty list for IN query)
    mock_result_settings = MagicMock()
    mock_result_settings.scalars.return_value.all.return_value = []

    # Mock DB select for AuditLog
    mock_result_audit = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result_audit.scalars.return_value.all.return_value = [mock_audit]

    # Route calls db.execute 1 time for settings IN query + 1 time for audit = 2 calls
    mock_db.execute.side_effect = [
        mock_result_settings,
        mock_result_audit,
    ]

    # Mock settings
    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.get_settings", lambda: mock_settings)

    # Mock render
    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.render", mock_render)

    # Call function
    from pit_panel.web.routes.settings import settings_update

    await settings_update(
        mock_request,
        base_domain="example.com",
        panel_subdomain="mypanel",
        abuseipdb_api_key="",
        sudo_password="",
        telegram_bot_token="",
        telegram_chat_id="",
        db=mock_db,
    )

    # Assert db.add_all was called for all 7 settings
    mock_db.add_all.assert_called_once()
    added_objects = mock_db.add_all.call_args[0][0]

    # Check added SystemSettings objects
    keys = [obj.key for obj in added_objects]
    assert keys == [
        "base_domain",
        "panel_subdomain",
        "host",
        "abuseipdb_api_key",
        "sudo_password",
        "telegram_bot_token",
        "telegram_chat_id",
    ]

    values = [obj.value for obj in added_objects]
    assert values == [
        {"v": "example.com"},
        {"v": "mypanel"},
        {"v": "127.0.0.1"},
        {"v": ""},
        {"v": ""},
        {"v": ""},
        {"v": ""},
    ]

    updated_bys = [obj.updated_by for obj in added_objects]
    assert updated_bys == [user.id] * 7

    # Assert commit called
    mock_db.commit.assert_awaited_once()

    # Assert in-memory settings were updated
    assert mock_settings.base_domain == "example.com"
    assert mock_settings.panel_subdomain == "mypanel"
    assert mock_settings.host == "127.0.0.1"

    # Assert render called
    mock_render.assert_called_once_with(
        "settings.html",
        user=user,
        audit_entries=[mock_audit],
        settings=mock_settings,
        config_saved=True,
        error=None,
    )


@pytest.mark.asyncio
async def test_settings_update_empty_panel(monkeypatch):
    # Setup mocks
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    # Mock DB select for SystemSettings
    mock_row_base = MagicMock()
    mock_row_panel = MagicMock()
    mock_row_host = MagicMock()
    mock_row_abuseipdb = MagicMock()
    mock_row_sudo = MagicMock()

    # Mock row setup
    mock_row_base.key = "base_domain"
    mock_row_panel.key = "panel_subdomain"
    mock_row_host.key = "host"
    mock_row_abuseipdb.key = "abuseipdb_api_key"
    mock_row_sudo.key = "sudo_password"
    mock_row_telegram_token = MagicMock()
    mock_row_telegram_token.key = "telegram_bot_token"
    mock_row_telegram_chat = MagicMock()
    mock_row_telegram_chat.key = "telegram_chat_id"

    mock_result_settings = MagicMock()
    mock_result_settings.scalars.return_value.all.return_value = [
        mock_row_base,
        mock_row_panel,
        mock_row_host,
        mock_row_abuseipdb,
        mock_row_sudo,
        mock_row_telegram_token,
        mock_row_telegram_chat,
    ]

    # Mock DB select for AuditLog
    mock_result_audit = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result_audit.scalars.return_value.all.return_value = [mock_audit]

    # Route calls db.execute 1 time for settings IN query + 1 time for audit = 2 calls
    mock_db.execute.side_effect = [
        mock_result_settings,
        mock_result_audit,
    ]

    # Mock settings
    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.get_settings", lambda: mock_settings)

    # Mock render
    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.render", mock_render)

    # Call function with empty base_domain and empty panel_subdomain
    from pit_panel.web.routes.settings import settings_update

    await settings_update(
        mock_request,
        base_domain="   ",
        panel_subdomain="   ",
        abuseipdb_api_key="",
        sudo_password="",
        telegram_bot_token="",
        telegram_chat_id="",
        db=mock_db,
    )

    # Assert SystemSettings were updated with fallbacks
    assert mock_row_base.value == {"v": ""}
    assert mock_row_panel.value == {"v": "panel"}  # fallback for panel
    assert mock_row_host.value == {"v": "0.0.0.0"}  # fallback for host since base_domain is empty

    # Assert in-memory settings were updated
    assert mock_settings.base_domain == ""
    assert mock_settings.panel_subdomain == "panel"
    assert mock_settings.host == "0.0.0.0"


@pytest.mark.asyncio
async def test_settings_update_invalid_base_domain(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)
    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    from pit_panel.web.routes.settings import settings_update

    response = await settings_update(
        mock_request,
        base_domain="invalid space",
        panel_subdomain="panel",
        abuseipdb_api_key="",
        sudo_password="",
        db=mock_db,
    )

    assert response.status_code == 400
    assert response.body == b"Invalid base domain"


@pytest.mark.asyncio
async def test_settings_update_invalid_panel_subdomain(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)
    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    from pit_panel.web.routes.settings import settings_update

    response = await settings_update(
        mock_request,
        base_domain="example.com",
        panel_subdomain="invalid space",
        abuseipdb_api_key="",
        sudo_password="",
        db=mock_db,
    )

    assert response.status_code == 400
    assert response.body == b"Invalid panel subdomain"


@pytest.mark.asyncio
async def test_audit_log_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    from pit_panel.web.routes.settings import audit_log

    response = await audit_log(mock_request, mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_audit_log_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)
    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.render", mock_render)

    mock_result = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result.scalars.return_value.all.return_value = [mock_audit]
    mock_db.execute.return_value = mock_result

    from pit_panel.web.routes.settings import audit_log

    await audit_log(mock_request, mock_db)

    mock_render.assert_called_once_with("audit.html", user=user, entries=[mock_audit])
    mock_db.execute.assert_called_once()

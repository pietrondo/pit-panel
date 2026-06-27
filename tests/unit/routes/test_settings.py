from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from pit_panel.db.models import AuditLog, User
from pit_panel.web.routes.settings import _load_db_settings, settings_page


@pytest.mark.asyncio
async def test_load_db_settings():
    # Setup mock db session
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()

    # Setup mock row objects
    mock_row_1 = MagicMock()
    mock_row_1.key = "base_domain"
    mock_row_1.value = "example.com"

    mock_row_2 = MagicMock()
    mock_row_2.key = "panel_subdomain"
    mock_row_2.value = "panel"

    mock_result.scalars.return_value.all.return_value = [mock_row_1, mock_row_2]
    mock_db.execute.return_value = mock_result

    # Call the function
    settings = await _load_db_settings(mock_db)

    # Assert results
    assert settings == {"base_domain": "example.com", "panel_subdomain": "panel"}
    mock_db.execute.assert_called_once()


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
        mock_request, base_domain="", panel_subdomain="panel", db=mock_db
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

    mock_result_base = MagicMock()
    mock_result_base.scalar_one_or_none.return_value = mock_row_base
    mock_result_panel = MagicMock()
    mock_result_panel.scalar_one_or_none.return_value = mock_row_panel
    mock_result_host = MagicMock()
    mock_result_host.scalar_one_or_none.return_value = mock_row_host

    # Mock DB select for AuditLog
    mock_result_audit = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result_audit.scalars.return_value.all.return_value = [mock_audit]

    # Return different mock results for multiple execute calls
    mock_db.execute.side_effect = [
        mock_result_base,
        mock_result_panel,
        mock_result_host,
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
        mock_request, base_domain=" newdomain.com ", panel_subdomain=" newpanel ", db=mock_db
    )

    # Assert SystemSettings were updated
    assert mock_row_base.value == {"v": "newdomain.com"}
    assert mock_row_base.updated_by == user.id
    assert mock_row_panel.value == {"v": "newpanel"}
    assert mock_row_panel.updated_by == user.id
    assert mock_row_host.value == {"v": "127.0.0.1"}
    assert mock_row_host.updated_by == user.id

    # Assert no new settings added
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

    # Mock DB select for SystemSettings (returns None for all rows)
    mock_result_settings = MagicMock()
    mock_result_settings.scalar_one_or_none.return_value = None

    # Mock DB select for AuditLog
    mock_result_audit = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result_audit.scalars.return_value.all.return_value = [mock_audit]

    # Return different mock results for multiple execute calls
    mock_db.execute.side_effect = [
        mock_result_settings,
        mock_result_settings,
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
        mock_request, base_domain="example.com", panel_subdomain="mypanel", db=mock_db
    )

    # Assert db.add was called for all 3 settings
    assert mock_db.add.call_count == 3
    added_objects = [call.args[0] for call in mock_db.add.call_args_list]

    # Check added SystemSettings objects
    keys = [obj.key for obj in added_objects]
    assert keys == ["base_domain", "panel_subdomain", "host"]

    values = [obj.value for obj in added_objects]
    assert values == [{"v": "example.com"}, {"v": "mypanel"}, {"v": "127.0.0.1"}]

    updated_bys = [obj.updated_by for obj in added_objects]
    assert updated_bys == [user.id, user.id, user.id]

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

    mock_result_base = MagicMock()
    mock_result_base.scalar_one_or_none.return_value = mock_row_base
    mock_result_panel = MagicMock()
    mock_result_panel.scalar_one_or_none.return_value = mock_row_panel
    mock_result_host = MagicMock()
    mock_result_host.scalar_one_or_none.return_value = mock_row_host

    # Mock DB select for AuditLog
    mock_result_audit = MagicMock()
    mock_audit = MagicMock(spec=AuditLog)
    mock_result_audit.scalars.return_value.all.return_value = [mock_audit]

    # Return different mock results for multiple execute calls
    mock_db.execute.side_effect = [
        mock_result_base,
        mock_result_panel,
        mock_result_host,
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

    await settings_update(mock_request, base_domain="   ", panel_subdomain="   ", db=mock_db)

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
        mock_request, base_domain="invalid space", panel_subdomain="panel", db=mock_db
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
        mock_request, base_domain="example.com", panel_subdomain="invalid space", db=mock_db
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

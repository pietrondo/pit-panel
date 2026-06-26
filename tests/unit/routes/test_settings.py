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

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from pit_panel.web.app import _lifespan, lifespan


@pytest.mark.asyncio
async def test_lifespan_applies_settings(settings):
    app = FastAPI()
    app.state.settings = settings
    app.state.settings.base_domain = ""
    app.state.settings.panel_subdomain = ""
    app.state.settings.port = 8000

    mock_row1 = MagicMock()
    mock_row1.key = "base_domain"
    mock_row1.value = "example.com"

    mock_row2 = MagicMock()
    mock_row2.key = "panel_subdomain"
    mock_row2.value = "admin"

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_row1, mock_row2]

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_db

    with patch("pit_panel.web.app.init_db", new_callable=AsyncMock) as mock_init_db, \
         patch("pit_panel.web.app.get_sessionmaker", return_value=mock_sessionmaker), \
         patch("pit_panel.core.caddy.CaddyManager", autospec=True) as mock_caddy_cls:

        mock_caddy = mock_caddy_cls.return_value
        mock_caddy.setup_panel_route = AsyncMock()

        async with lifespan(app):
            pass

        mock_init_db.assert_awaited_once_with(settings)
        assert app.state.settings.base_domain == "example.com"
        assert app.state.settings.panel_subdomain == "admin"

        mock_caddy.setup_panel_route.assert_awaited_once_with("admin", "example.com", 8000)

@pytest.mark.asyncio
async def test_lifespan_updates_dict_value(settings):
    app = FastAPI()
    app.state.settings = settings
    app.state.settings.base_domain = ""

    mock_row1 = MagicMock()
    mock_row1.key = "base_domain"
    mock_row1.value = {"v": "test.com"}

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_row1]

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_db

    with patch("pit_panel.web.app.init_db", new_callable=AsyncMock), \
         patch("pit_panel.web.app.get_sessionmaker", return_value=mock_sessionmaker), \
         patch("pit_panel.core.caddy.CaddyManager"):

        async with lifespan(app):
            pass

        assert app.state.settings.base_domain == "test.com"

@pytest.mark.asyncio
async def test_lifespan_no_caddy_if_missing_settings(settings):
    app = FastAPI()
    app.state.settings = settings
    # Missing panel_subdomain or base_domain effectively
    app.state.settings.base_domain = ""
    app.state.settings.panel_subdomain = ""

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [] # No updates

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_db

    with patch("pit_panel.web.app.init_db", new_callable=AsyncMock), \
         patch("pit_panel.web.app.get_sessionmaker", return_value=mock_sessionmaker), \
         patch("pit_panel.core.caddy.CaddyManager") as mock_caddy_cls, \
         patch("pit_panel.config.Settings.effective_domain", ""): # Force no effective domain

        async with lifespan(app):
            pass

        mock_caddy_cls.assert_not_called()


@pytest.mark.asyncio
async def test_internal_lifespan_creates_cancels_task():
    app = FastAPI()

    mock_task = asyncio.Future()
    mock_task.cancel = MagicMock()

    with patch("asyncio.create_task", return_value=mock_task) as mock_create, \
         patch("pit_panel.core.blocklist.daily_blocklist_import", new_callable=MagicMock):

        async with _lifespan(app):
            mock_create.assert_called_once()
            mock_task.cancel.assert_not_called()

            # satisfy the await task
            mock_task.set_result(None)

        mock_task.cancel.assert_called_once()

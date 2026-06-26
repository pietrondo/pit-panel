from unittest.mock import AsyncMock, Mock

import pytest

from pit_panel.web.auth import SESSION_COOKIE
from pit_panel.web.deps import get_user


@pytest.fixture
def mock_get_settings(monkeypatch, settings):
    monkeypatch.setattr("pit_panel.web.deps.get_settings", lambda: settings)
    return settings


@pytest.mark.asyncio
async def test_get_user_no_cookie(mock_get_settings):
    request = Mock()
    request.cookies.get.return_value = None
    db = AsyncMock()

    result = await get_user(request, db)
    assert result is None
    request.cookies.get.assert_called_once_with(SESSION_COOKIE)


@pytest.mark.asyncio
async def test_get_user_invalid_token(monkeypatch, mock_get_settings):
    request = Mock()
    request.cookies.get.return_value = "invalid_cookie"
    db = AsyncMock()

    monkeypatch.setattr("pit_panel.web.deps.unsign_session_token", lambda s, c: None)

    result = await get_user(request, db)
    assert result is None


@pytest.mark.asyncio
async def test_get_user_no_uid(monkeypatch, mock_get_settings):
    request = Mock()
    request.cookies.get.return_value = "valid_cookie_no_uid"
    db = AsyncMock()

    monkeypatch.setattr("pit_panel.web.deps.unsign_session_token", lambda s, c: {"other": "data"})

    result = await get_user(request, db)
    assert result is None


@pytest.mark.asyncio
async def test_get_user_failed_validation(monkeypatch, mock_get_settings):
    request = Mock()
    request.cookies.get.return_value = "valid_cookie"
    db = AsyncMock()

    monkeypatch.setattr("pit_panel.web.deps.unsign_session_token", lambda s, c: {"uid": 1})

    mock_validate = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate)

    result = await get_user(request, db)
    assert result is None
    mock_validate.assert_called_once()


@pytest.mark.asyncio
async def test_get_user_success(monkeypatch, mock_get_settings):
    request = Mock()
    request.cookies.get.return_value = "valid_cookie"
    db = AsyncMock()

    monkeypatch.setattr("pit_panel.web.deps.unsign_session_token", lambda s, c: {"uid": 1})

    mock_user = Mock()
    mock_validate = AsyncMock(return_value=mock_user)
    monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate)

    result = await get_user(request, db)
    assert result is mock_user
    mock_validate.assert_called_once()

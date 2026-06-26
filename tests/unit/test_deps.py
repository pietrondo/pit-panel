from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import HTTPException, Request

from pit_panel.config import Settings
from pit_panel.db.models import User
from pit_panel.web.auth import SESSION_COOKIE
from pit_panel.web.deps import get_current_user, get_user


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.cookies = {}
    return request

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_settings():
    return Settings(secret_key="test-secret-key-32chars-long!!", debug=True)

@pytest.mark.asyncio
async def test_get_current_user_no_cookie(mock_request, mock_db, mock_settings):
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(mock_request, mock_db, mock_settings)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Not authenticated"

@pytest.mark.asyncio
async def test_get_current_user_no_uid(mock_request, mock_db, mock_settings, monkeypatch):
    mock_request.cookies[SESSION_COOKIE] = "fake_cookie"

    mock_loads = MagicMock(return_value={"some_other_key": 123})
    mock_serializer = MagicMock()
    mock_serializer.loads = mock_loads

    def mock_url_safe_timed_serializer(*args, **kwargs):
        return mock_serializer

    class MockItsDangerous:
        URLSafeTimedSerializer = mock_url_safe_timed_serializer

    original_import = __builtins__["__import__"]

    def import_mock(name, *args, **kwargs):
        if name == "itsdangerous":
            return MockItsDangerous()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", import_mock)

    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(mock_request, mock_db, mock_settings)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_current_user_invalid_session(mock_request, mock_db, mock_settings, monkeypatch):
    mock_request.cookies[SESSION_COOKIE] = "fake_cookie"

    mock_loads = MagicMock(return_value={"uid": 1})
    mock_serializer = MagicMock()
    mock_serializer.loads = mock_loads

    def mock_url_safe_timed_serializer(*args, **kwargs):
        return mock_serializer

    class MockItsDangerous:
        URLSafeTimedSerializer = mock_url_safe_timed_serializer

    original_import = __builtins__["__import__"]

    def import_mock(name, *args, **kwargs):
        if name == "itsdangerous":
            return MockItsDangerous()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", import_mock)

    async def mock_validate_session(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate_session)

    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(mock_request, mock_db, mock_settings)
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_current_user_success(mock_request, mock_db, mock_settings, monkeypatch):
    mock_request.cookies[SESSION_COOKIE] = "fake_cookie"

    mock_loads = MagicMock(return_value={"uid": 1})
    mock_serializer = MagicMock()
    mock_serializer.loads = mock_loads

    def mock_url_safe_timed_serializer(*args, **kwargs):
        return mock_serializer

    class MockItsDangerous:
        URLSafeTimedSerializer = mock_url_safe_timed_serializer

    original_import = __builtins__["__import__"]

    def import_mock(name, *args, **kwargs):
        if name == "itsdangerous":
            return MockItsDangerous()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", import_mock)

    mock_user = User(id=1, username="admin")
    async def mock_validate_session(*args, **kwargs):
        return mock_user

    monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate_session)

    user = await get_current_user(mock_request, mock_db, mock_settings)
    assert user == mock_user


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

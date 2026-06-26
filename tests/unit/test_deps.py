import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request, HTTPException

from pit_panel.web.deps import get_current_user
from pit_panel.db.models import User
from pit_panel.config import Settings
from pit_panel.web.auth import SESSION_COOKIE

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
    monkeypatch.setattr("builtins.__import__", lambda name, *args, **kwargs: MockItsDangerous() if name == "itsdangerous" else original_import(name, *args, **kwargs))

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
    monkeypatch.setattr("builtins.__import__", lambda name, *args, **kwargs: MockItsDangerous() if name == "itsdangerous" else original_import(name, *args, **kwargs))

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
    monkeypatch.setattr("builtins.__import__", lambda name, *args, **kwargs: MockItsDangerous() if name == "itsdangerous" else original_import(name, *args, **kwargs))

    mock_user = User(id=1, username="admin")
    async def mock_validate_session(*args, **kwargs):
        return mock_user

    monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate_session)

    user = await get_current_user(mock_request, mock_db, mock_settings)
    assert user == mock_user

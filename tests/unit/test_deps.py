from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from pit_panel.db.models import User
from pit_panel.web.auth import SESSION_COOKIE
from pit_panel.web.deps import get_admin, get_current_user, get_user


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.cookies = {}
    return request


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def settings():
    from pit_panel.config import Settings

    return Settings(secret_key="test-secret-key-32chars-long!!")


@pytest.mark.asyncio
class TestGetUser:
    async def test_no_cookie(self, mock_request, mock_db):
        mock_request.cookies = {}
        user = await get_user(mock_request, mock_db)
        assert user is None

    async def test_invalid_cookie(self, mock_request, mock_db, monkeypatch, settings):
        mock_request.cookies = {SESSION_COOKIE: "invalid"}
        monkeypatch.setattr("pit_panel.web.deps.get_settings", lambda: settings)
        monkeypatch.setattr("pit_panel.web.deps.unsign_session_token", lambda s, c: None)

        user = await get_user(mock_request, mock_db)
        assert user is None

    async def test_missing_uid(self, mock_request, mock_db, monkeypatch, settings):
        mock_request.cookies = {SESSION_COOKIE: "valid"}
        monkeypatch.setattr("pit_panel.web.deps.get_settings", lambda: settings)
        monkeypatch.setattr(
            "pit_panel.web.deps.unsign_session_token", lambda s, c: {"other": "data"}
        )

        user = await get_user(mock_request, mock_db)
        assert user is None

    async def test_invalid_session(self, mock_request, mock_db, monkeypatch, settings):
        mock_request.cookies = {SESSION_COOKIE: "valid"}
        monkeypatch.setattr("pit_panel.web.deps.get_settings", lambda: settings)
        monkeypatch.setattr("pit_panel.web.deps.unsign_session_token", lambda s, c: {"uid": 1})

        async def mock_validate(*args, **kwargs):
            return None

        monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate)

        user = await get_user(mock_request, mock_db)
        assert user is None

    async def test_valid_session(self, mock_request, mock_db, monkeypatch, settings):
        mock_request.cookies = {SESSION_COOKIE: "valid"}
        monkeypatch.setattr("pit_panel.web.deps.get_settings", lambda: settings)
        monkeypatch.setattr("pit_panel.web.deps.unsign_session_token", lambda s, c: {"uid": 1})

        expected_user = User(id=1, username="test")

        async def mock_validate(*args, **kwargs):
            return expected_user

        monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate)

        user = await get_user(mock_request, mock_db)
        assert user == expected_user


@pytest.mark.asyncio
class TestGetCurrentUser:
    async def test_no_cookie(self, mock_request, mock_db, settings):
        mock_request.cookies = {}
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, mock_db, settings)
        assert exc.value.status_code == 401

    async def test_invalid_cookie(self, mock_request, mock_db, settings):
        mock_request.cookies = {SESSION_COOKIE: "invalid"}
        import itsdangerous

        with pytest.raises(itsdangerous.BadSignature):
            await get_current_user(mock_request, mock_db, settings)

    async def test_missing_uid(self, mock_request, mock_db, settings, monkeypatch):
        mock_request.cookies = {SESSION_COOKIE: "valid"}

        class MockSerializer:
            def loads(self, cookie):
                return {"other": "data"}

        monkeypatch.setattr(
            "itsdangerous.URLSafeTimedSerializer", lambda *args, **kwargs: MockSerializer()
        )

        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, mock_db, settings)
        assert exc.value.status_code == 401

    async def test_invalid_session(self, mock_request, mock_db, settings, monkeypatch):
        mock_request.cookies = {SESSION_COOKIE: "valid"}

        class MockSerializer:
            def loads(self, cookie):
                return {"uid": 1}

        monkeypatch.setattr(
            "itsdangerous.URLSafeTimedSerializer", lambda *args, **kwargs: MockSerializer()
        )

        async def mock_validate(*args, **kwargs):
            return None

        monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate)

        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, mock_db, settings)
        assert exc.value.status_code == 401

    async def test_valid_session(self, mock_request, mock_db, settings, monkeypatch):
        mock_request.cookies = {SESSION_COOKIE: "valid"}

        class MockSerializer:
            def loads(self, cookie):
                return {"uid": 1}

        monkeypatch.setattr(
            "itsdangerous.URLSafeTimedSerializer", lambda *args, **kwargs: MockSerializer()
        )

        expected_user = User(id=1, username="test")

        async def mock_validate(*args, **kwargs):
            return expected_user

        monkeypatch.setattr("pit_panel.web.deps.validate_session", mock_validate)

        user = await get_current_user(mock_request, mock_db, settings)
        assert user == expected_user


@pytest.mark.asyncio
class TestGetAdmin:
    async def test_not_logged_in(self, mock_request, mock_db, monkeypatch):
        async def mock_get_user(*args, **kwargs):
            return None

        monkeypatch.setattr("pit_panel.web.deps.get_user", mock_get_user)

        admin = await get_admin(mock_request, mock_db)
        assert admin is None

    async def test_logged_in_not_admin(self, mock_request, mock_db, monkeypatch):
        async def mock_get_user(*args, **kwargs):
            return User(id=1, is_admin=False)

        monkeypatch.setattr("pit_panel.web.deps.get_user", mock_get_user)

        admin = await get_admin(mock_request, mock_db)
        assert admin is None

    async def test_logged_in_is_admin(self, mock_request, mock_db, monkeypatch):
        expected_user = User(id=1, is_admin=True)

        async def mock_get_user(*args, **kwargs):
            return expected_user

        monkeypatch.setattr("pit_panel.web.deps.get_user", mock_get_user)

        admin = await get_admin(mock_request, mock_db)
        assert admin == expected_user

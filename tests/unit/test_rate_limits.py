from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from pit_panel.db.session import get_db
from pit_panel.web.limiter import limiter
from pit_panel.web.routes.auth_routes import router as auth_router
from pit_panel.web.routes.file_manager import router as file_router
from pit_panel.web.routes.settings import router as settings_router


@pytest.fixture
def client():
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_router)
    app.include_router(settings_router)
    app.include_router(file_router)

    # Set up generic mock DB that returns None/empty list for queries
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: db

    limiter.reset()

    return TestClient(app)


def test_setup_2fa_rate_limit(client, monkeypatch):
    async def mock_get_user(req, db):
        return MagicMock(totp_secret="secret", username="user")

    monkeypatch.setattr("pit_panel.web.routes.auth_routes.get_user", mock_get_user)
    monkeypatch.setattr("pit_panel.web.routes.auth_routes.verify_totp", lambda secret, code: True)
    monkeypatch.setattr(
        "pit_panel.web.routes.auth_routes.render",
        lambda *args, **kwargs: "rendered",
    )

    for _ in range(5):
        resp = client.post("/setup-2fa", data={"code": "123456"})
        assert resp.status_code != 429

    resp = client.post("/setup-2fa", data={"code": "123456"})
    assert resp.status_code == 429


def test_settings_update_rate_limit(client, monkeypatch):
    async def mock_get_admin(req, db):
        return MagicMock(id=1)

    monkeypatch.setattr("pit_panel.web.routes.settings.get_admin", mock_get_admin)
    monkeypatch.setattr("pit_panel.web.routes.settings.render", lambda *args, **kwargs: "rendered")

    # Mock settings.save_config_file to prevent writing to config file
    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.settings.get_settings", lambda: mock_settings)

    for _ in range(10):
        resp = client.post(
            "/settings/update",
            data={
                "base_domain": "example.com",
                "panel_subdomain": "panel",
                "abuseipdb_api_key": "apikey",
                "sudo_password": "sudo",
                "telegram_bot_token": "token",
                "telegram_chat_id": "chatid",
            },
        )
        assert resp.status_code != 429

    resp = client.post(
        "/settings/update",
        data={
            "base_domain": "example.com",
            "panel_subdomain": "panel",
            "abuseipdb_api_key": "apikey",
            "sudo_password": "sudo",
            "telegram_bot_token": "token",
            "telegram_chat_id": "chatid",
        },
    )
    assert resp.status_code == 429


def test_file_save_rate_limit(client, monkeypatch):
    async def mock_get_admin(req, db):
        return MagicMock(id=1)

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)
    monkeypatch.setattr("pit_panel.web.routes.file_manager.verify_safe_path", lambda p: MagicMock())

    for _ in range(20):
        resp = client.post(
            "/api/file-manager/save",
            json={"path": "/opt/pit-panel/file.txt", "content": "hello"},
        )
        assert resp.status_code != 429

    resp = client.post(
        "/api/file-manager/save",
        json={"path": "/opt/pit-panel/file.txt", "content": "hello"},
    )
    assert resp.status_code == 429

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from pit_panel.db.session import get_db
from pit_panel.web.routes.settings import router

app = FastAPI()
app.include_router(router)


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class MockResult:
    def scalars(self):
        class MockScalars:
            def all(self):
                return []

        return MockScalars()


class MockDB:
    async def execute(self, query):
        return MockResult()

    def add_all(self, items):
        pass

    async def commit(self):
        pass


async def mock_get_db():
    yield MockDB()


@pytest.fixture
def mock_db():
    app.dependency_overrides[get_db] = mock_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_admin():
    class MockUser:
        id = 1

    with patch("pit_panel.web.routes.settings.get_admin", new_callable=AsyncMock) as mock:
        mock.return_value = MockUser()
        yield mock


@pytest.fixture
def mock_no_admin():
    with patch("pit_panel.web.routes.settings.get_admin", new_callable=AsyncMock) as mock:
        mock.return_value = None
        yield mock


@pytest.mark.asyncio
async def test_settings_page_unauthorized(mock_db, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/settings")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_settings_page_success(mock_db, mock_admin):
    with (
        patch("pit_panel.web.routes.settings.get_settings"),
        patch("pit_panel.web.routes.settings.render") as mock_render,
    ):
        mock_render.return_value = "rendered html"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/settings")
        assert response.status_code == 200
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        assert args[0] == "settings.html"


@pytest.mark.asyncio
async def test_settings_update_unauthorized(mock_db, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/settings/update", data={"base_domain": "test.com"})
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_settings_update_invalid_domain(mock_db, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/settings/update", data={"base_domain": "invalid_domain!"})
    assert response.status_code == 400
    assert "Invalid base domain" in response.text


@pytest.mark.asyncio
async def test_settings_update_invalid_subdomain(mock_db, mock_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        data = {"base_domain": "test.com", "panel_subdomain": "invalid!"}
        response = await ac.post("/settings/update", data=data)
    assert response.status_code == 400
    assert "Invalid panel subdomain" in response.text


@pytest.mark.asyncio
async def test_settings_update_success(mock_db, mock_admin):
    with (
        patch("pit_panel.web.routes.settings.get_settings") as mock_get_settings,
        patch("pit_panel.web.routes.settings.render") as mock_render,
    ):
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        mock_render.return_value = "rendered html"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/settings/update",
                data={
                    "base_domain": "test.com",
                    "panel_subdomain": "panel",
                    "abuseipdb_api_key": "test_key",
                    "sudo_password": "test_pass",
                    "telegram_bot_token": "test_token",
                    "telegram_chat_id": "test_id",
                },
            )
        assert response.status_code == 200
        mock_settings.save_config_file.assert_called_once()
        assert mock_settings.base_domain == "test.com"


@pytest.mark.asyncio
async def test_settings_update_success_existing_rows(mock_admin):
    class MockExistingRow:
        def __init__(self, key):
            self.key = key
            self.value = {}
            self.updated_by = None

    existing_row_base_domain = MockExistingRow("base_domain")

    class MockResultExisting:
        def scalars(self):
            class MockScalars:
                def all(self):
                    return [existing_row_base_domain]

            return MockScalars()

    class MockDBExisting(MockDB):
        async def execute(self, query):
            # The query will be for IN('base_domain', 'panel_subdomain', ...)
            # Let's stringify the statement properly to check for SystemSettings
            query_str = str(query)
            if "system_settings" in query_str:
                return MockResultExisting()
            return MockResult()

    app.dependency_overrides[get_db] = lambda: MockDBExisting()

    with (
        patch("pit_panel.web.routes.settings.get_settings") as mock_get_settings,
        patch("pit_panel.web.routes.settings.render") as mock_render,
    ):
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        mock_render.return_value = "rendered html"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/settings/update",
                data={
                    "base_domain": "test2.com",
                    "panel_subdomain": "panel2",
                    "abuseipdb_api_key": "",
                    "sudo_password": "",
                    "telegram_bot_token": "",
                    "telegram_chat_id": "",
                },
            )

        assert response.status_code == 200
        assert existing_row_base_domain.value == {"v": "test2.com"}
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_audit_log_unauthorized(mock_db, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/settings/audit")
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_audit_log_success(mock_db, mock_admin):
    with patch("pit_panel.web.routes.settings.render") as mock_render:
        mock_render.return_value = "rendered html"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/settings/audit")
        assert response.status_code == 200
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        assert args[0] == "audit.html"


@pytest.mark.asyncio
async def test_settings_test_notification_unauthorized(mock_db, mock_no_admin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/settings/test-notification")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_settings_test_notification_success(mock_db, mock_admin):
    with patch("pit_panel.core.notifier.notify_test", new_callable=AsyncMock) as mock_notify_test:
        mock_notify_test.return_value = True
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/settings/test-notification")
        assert response.status_code == 200
        assert "Sent ✓" in response.text


@pytest.mark.asyncio
async def test_settings_test_notification_fail(mock_db, mock_admin):
    with patch("pit_panel.core.notifier.notify_test", new_callable=AsyncMock) as mock_notify_test:
        mock_notify_test.return_value = False
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/settings/test-notification")
        assert response.status_code == 200
        assert "Failed" in response.text

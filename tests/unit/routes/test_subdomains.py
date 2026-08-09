import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db

@pytest.fixture
def test_client(mock_db):
    from pit_panel.web.app import create_app
    from pit_panel.db.session import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock the ipban middleware dependency to prevent database issues
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock) as mock_banned:
        mock_banned.return_value = False
        yield TestClient(app)

@pytest.fixture
def mock_settings():
    with patch("pit_panel.web.routes.subdomains.get_settings") as mock:
        settings = MagicMock()
        settings.base_domain = "example.com"
        settings.caddy_admin_url = "http://localhost:2019"
        mock.return_value = settings
        yield mock

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomains_list_unauthenticated(mock_get_user, test_client):
    mock_get_user.return_value = None
    response = test_client.get("/subdomains", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomains_list_authenticated(mock_get_user, test_client, mock_db):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        MagicMock(id=1, subdomain="test1", base_domain="example.com", is_main_domain=False),
        MagicMock(id=2, subdomain="test2", base_domain="example.com", is_main_domain=False),
    ]
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("pit_panel.web.routes.subdomains.render") as mock_render:
        mock_render.return_value = "rendered html"
        response = test_client.get("/subdomains")

        assert response.status_code == 200
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        assert args[0] == "subdomains.html"
        assert kwargs["user"] == mock_user
        assert len(kwargs["subdomains"]) == 2

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_add_unauthenticated(mock_get_user, test_client):
    mock_get_user.return_value = None
    response = test_client.post("/subdomains/add", data={"subdomain": "test", "app_type": "none"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
@patch("pit_panel.web.routes.subdomains._log_audit")
@patch("pit_panel.web.routes.subdomains.CaddyManager")
async def test_subdomain_add_success(mock_caddy, mock_audit, mock_get_user, test_client, mock_db, mock_settings):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    mock_caddy_instance = MagicMock()
    mock_caddy_instance.add_subdomain = AsyncMock()
    mock_caddy_instance.renew_certificate = AsyncMock()
    mock_caddy.return_value = mock_caddy_instance

    response = test_client.post("/subdomains/add", data={"subdomain": "test-sub", "app_type": "none"}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains"
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_audit.assert_called_once()
    mock_caddy.assert_called_once_with(mock_settings().caddy_admin_url)
    mock_caddy_instance.add_subdomain.assert_called_once_with("test-sub", "example.com")
    mock_caddy_instance.renew_certificate.assert_called_once_with("test-sub.example.com")

@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_name", ["invalid_name!", "../test", "test/123", "-test", "test-", " "])
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_add_invalid_name(mock_get_user, test_client, mock_db, mock_settings, invalid_name):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("pit_panel.web.routes.subdomains.render") as mock_render:
        mock_render.return_value = "rendered html"
        response = test_client.post("/subdomains/add", data={"subdomain": invalid_name, "app_type": "none"})

        assert response.status_code == 200
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        assert kwargs["error"] == "Invalid subdomain name"
        mock_db.add.assert_not_called()

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_add_already_exists(mock_get_user, test_client, mock_db, mock_settings):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    existing_subdomain = MagicMock()
    mock_execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_subdomain), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    mock_db.execute = mock_execute

    with patch("pit_panel.web.routes.subdomains.render") as mock_render:
        mock_render.return_value = "rendered html"
        response = test_client.post("/subdomains/add", data={"subdomain": "test", "app_type": "none"})

        assert response.status_code == 200
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        assert kwargs["error"] == "Subdomain already exists"
        mock_db.add.assert_not_called()

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_edit_unauthenticated(mock_get_user, test_client):
    mock_get_user.return_value = None
    response = test_client.post("/subdomains/1/edit", data={"subdomain": "test", "app_type": "none"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
@patch("pit_panel.web.routes.subdomains._log_audit")
@patch("pit_panel.web.routes.subdomains.CaddyManager")
async def test_subdomain_edit_success(mock_caddy, mock_audit, mock_get_user, test_client, mock_db, mock_settings):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    existing_sd = MagicMock()
    existing_sd.id = 1
    existing_sd.is_main_domain = False
    existing_sd.subdomain = "old-sub"
    existing_sd.app_type = None

    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_sd)))

    mock_caddy_instance = MagicMock()
    mock_caddy_instance.add_subdomain = AsyncMock()
    mock_caddy_instance.remove_subdomain = AsyncMock()
    mock_caddy.return_value = mock_caddy_instance

    response = test_client.post("/subdomains/1/edit", data={"subdomain": "new-sub", "app_type": "wordpress"}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains"
    assert existing_sd.subdomain == "new-sub"
    assert existing_sd.app_type == "wordpress"
    mock_db.commit.assert_called_once()
    mock_audit.assert_called_once()
    mock_caddy_instance.remove_subdomain.assert_called_once_with("old-sub", "example.com")
    mock_caddy_instance.add_subdomain.assert_called_once_with("new-sub", "example.com")

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_edit_not_found(mock_get_user, test_client, mock_db):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    response = test_client.post("/subdomains/1/edit", data={"subdomain": "new-sub", "app_type": "wordpress"}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains"
    mock_db.commit.assert_not_called()

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_delete_unauthenticated(mock_get_user, test_client):
    mock_get_user.return_value = None
    response = test_client.post("/subdomains/1/delete", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
@patch("pit_panel.web.routes.subdomains._log_audit")
@patch("pit_panel.web.routes.subdomains.CaddyManager")
async def test_subdomain_delete_success(mock_caddy, mock_audit, mock_get_user, test_client, mock_db, mock_settings):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    existing_sd = MagicMock()
    existing_sd.id = 1
    existing_sd.is_main_domain = False
    existing_sd.subdomain = "test-sub"

    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_sd)))

    mock_caddy_instance = MagicMock()
    mock_caddy_instance.remove_subdomain = AsyncMock()
    mock_caddy.return_value = mock_caddy_instance

    response = test_client.post("/subdomains/1/delete", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains"
    mock_db.delete.assert_called_once_with(existing_sd)
    mock_db.commit.assert_called_once()
    mock_audit.assert_called_once()
    mock_caddy_instance.remove_subdomain.assert_called_once_with("test-sub", "example.com")

@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_delete_not_found(mock_get_user, test_client, mock_db):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    response = test_client.post("/subdomains/1/delete", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains"
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_log_audit_helper():
    from pit_panel.web.routes.subdomains import _log_audit
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "pytest-agent"

    await _log_audit(mock_db, 1, "test_action", "test_type", 123, {"key": "value"}, mock_request)

    mock_db.add.assert_called_once()
    added_entry = mock_db.add.call_args[0][0]
    assert added_entry.user_id == 1
    assert added_entry.action == "test_action"
    assert added_entry.target_type == "test_type"
    assert added_entry.target_id == 123
    assert added_entry.details == {"key": "value"}
    assert added_entry.ip == "127.0.0.1"
    assert added_entry.user_agent == "pytest-agent"
    mock_db.commit.assert_called_once()

    # Test without client
    mock_db.reset_mock()
    mock_request.client = None

    await _log_audit(mock_db, 1, "test_action", "test_type", 123, {"key": "value"}, mock_request)
    mock_db.add.assert_called_once()
    added_entry_no_client = mock_db.add.call_args[0][0]
    assert added_entry_no_client.ip is None

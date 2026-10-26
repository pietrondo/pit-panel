from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def test_client(mock_db):
    from pit_panel.db.session import get_db
    from pit_panel.web.app import create_app

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
        settings.effective_domain = "example.com"
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
    response = test_client.post(
        "/subdomains/add", data={"subdomain": "test", "app_type": "none"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
@patch("pit_panel.web.routes.subdomains._log_audit")
@patch("pit_panel.web.routes.subdomains.CaddyManager")
async def test_subdomain_add_success(
    mock_caddy, mock_audit, mock_get_user, test_client, mock_db, mock_settings
):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    mock_caddy_instance = MagicMock()
    mock_caddy_instance.add_subdomain = AsyncMock()
    mock_caddy_instance.renew_certificate = AsyncMock()
    mock_caddy.return_value = mock_caddy_instance

    response = test_client.post(
        "/subdomains/add",
        data={"subdomain": "test-sub", "app_type": "none"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains?created=test-sub.example.com"
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_audit.assert_called_once()
    # A name has nothing to proxy: the route is created by the app deployment,
    # which is the only place that knows the port.
    mock_caddy.assert_not_called()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
@patch("pit_panel.web.routes.subdomains._log_audit")
@patch("pit_panel.web.routes.subdomains.CaddyManager")
async def test_subdomain_add_uses_effective_domain_when_custom_domain_is_unset(
    mock_caddy, mock_audit, mock_get_user, test_client, mock_db
):
    mock_user = MagicMock(id=1)
    mock_get_user.return_value = mock_user
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    settings = MagicMock(
        base_domain="", effective_domain="203-0-113-42.nip.io", caddy_admin_url="http://localhost:2019"
    )
    mock_caddy_instance = MagicMock()
    mock_caddy_instance.add_subdomain = AsyncMock()
    mock_caddy_instance.renew_certificate = AsyncMock()
    mock_caddy.return_value = mock_caddy_instance

    with patch("pit_panel.web.routes.subdomains.get_settings", return_value=settings):
        response = test_client.post(
            "/subdomains/add", data={"subdomain": "customer", "app_type": "none"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    added = mock_db.add.call_args.args[0]
    assert added.base_domain == "203-0-113-42.nip.io"
    mock_caddy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_name", ["invalid_name!", "../test", "test/123", "-test", "test-", " "]
)
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_add_invalid_name(
    mock_get_user, test_client, mock_db, mock_settings, invalid_name
):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("pit_panel.web.routes.subdomains.render") as mock_render:
        mock_render.return_value = "rendered html"
        response = test_client.post(
            "/subdomains/add", data={"subdomain": invalid_name, "app_type": "none"}
        )

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
    mock_execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=existing_subdomain),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        )
    )
    mock_db.execute = mock_execute

    with patch("pit_panel.web.routes.subdomains.render") as mock_render:
        mock_render.return_value = "rendered html"
        response = test_client.post(
            "/subdomains/add", data={"subdomain": "test", "app_type": "none"}
        )

        assert response.status_code == 200
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        assert kwargs["error"] == "Subdomain already exists"
        mock_db.add.assert_not_called()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_edit_unauthenticated(mock_get_user, test_client):
    mock_get_user.return_value = None
    response = test_client.post(
        "/subdomains/1/edit", data={"subdomain": "test", "app_type": "none"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
@patch("pit_panel.web.routes.subdomains._log_audit")
@patch("pit_panel.web.routes.subdomains.CaddyManager")
async def test_subdomain_edit_success(
    mock_caddy, mock_audit, mock_get_user, test_client, mock_db, mock_settings
):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    existing_sd = MagicMock()
    existing_sd.id = 1
    existing_sd.is_main_domain = False
    existing_sd.subdomain = "old-sub"
    existing_sd.app_type = None
    existing_sd.base_domain = "203-0-113-42.nip.io"
    existing_sd.host_port = 80

    mock_db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=existing_sd)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
    )

    mock_caddy_instance = MagicMock()
    mock_caddy_instance.add_subdomain = AsyncMock()
    mock_caddy_instance.remove_subdomain = AsyncMock()
    mock_caddy.return_value = mock_caddy_instance

    response = test_client.post(
        "/subdomains/1/edit",
        data={"subdomain": "new-sub"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains"
    assert existing_sd.subdomain == "new-sub"
    mock_db.commit.assert_called_once()
    mock_audit.assert_called_once()
    mock_caddy_instance.remove_subdomain.assert_called_once_with("old-sub", "203-0-113-42.nip.io")
    mock_caddy_instance.add_subdomain.assert_called_once_with(
        "new-sub", "203-0-113-42.nip.io", port=80
    )


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_edit_rejects_name_owned_by_another_user(
    mock_get_user, test_client, mock_db, mock_settings
):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    existing_sd = MagicMock()
    existing_sd.id = 1
    existing_sd.is_main_domain = False
    existing_sd.subdomain = "old-sub"
    existing_sd.app_type = None
    existing_sd.base_domain = "203-0-113-42.nip.io"
    existing_sd.host_port = 80

    clash = MagicMock()
    clash.id = 2

    # First query loads the edited subdomain, the second one looks for the new name.
    mock_db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=existing_sd)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=clash)),
        ]
    )

    response = test_client.post(
        "/subdomains/1/edit",
        data={"subdomain": "taken-sub", "app_type": "none"},
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert "already exists" in response.text
    assert existing_sd.subdomain == "old-sub"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_edit_not_found(mock_get_user, test_client, mock_db):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    response = test_client.post(
        "/subdomains/1/edit",
        data={"subdomain": "new-sub", "app_type": "wordpress"},
        follow_redirects=False,
    )

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
async def test_subdomain_delete_success(
    mock_caddy, mock_audit, mock_get_user, test_client, mock_db, mock_settings
):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    existing_sd = MagicMock()
    existing_sd.id = 1
    existing_sd.is_main_domain = False
    existing_sd.subdomain = "test-sub"
    existing_sd.base_domain = "203-0-113-42.nip.io"

    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_sd))
    )

    mock_caddy_instance = MagicMock()
    mock_caddy_instance.remove_subdomain = AsyncMock()
    mock_caddy.return_value = mock_caddy_instance

    response = test_client.post("/subdomains/1/delete", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/subdomains"
    mock_db.delete.assert_called_once_with(existing_sd)
    mock_db.commit.assert_called_once()
    mock_audit.assert_called_once()
    mock_caddy_instance.remove_subdomain.assert_called_once_with(
        "test-sub", "203-0-113-42.nip.io"
    )


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
async def test_subdomain_delete_not_found(mock_get_user, test_client, mock_db):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_user.return_value = mock_user

    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

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


@pytest.mark.asyncio
async def test_dns_add_skips_roots_the_account_does_not_own(monkeypatch):
    from types import SimpleNamespace

    from pit_panel.web.routes import subdomains as subdomains_module

    async def account_roots(_settings):
        return ["owned.dynu.net"]

    monkeypatch.setattr(subdomains_module, "available_roots", account_roots)
    settings = SimpleNamespace(dynu_api_key="key", dynu_domain="owned.dynu.net")

    # Legacy subdomains keep their own base domain: no Dynu record is provisioned for them.
    assert (
        await subdomains_module._dns_add(settings, "customer", "legacy.example.com") is None
    )


@pytest.mark.asyncio
@patch("pit_panel.web.routes.subdomains.get_user")
@patch("pit_panel.web.routes.subdomains._dns_add")
@patch("pit_panel.web.routes.subdomains.available_roots")
@patch("pit_panel.web.routes.subdomains.get_settings")
async def test_subdomain_add_can_use_any_root_of_the_account(
    mock_get_settings, mock_roots, mock_dns, mock_get_user, test_client, mock_db
):
    from types import SimpleNamespace

    mock_get_user.return_value = MagicMock(id=1, is_admin=True)
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    mock_get_settings.return_value = SimpleNamespace(
        dynu_api_key="key",
        dynu_domain="one.dynu.net",
        effective_domain="one.dynu.net",
    )
    mock_roots.return_value = ["one.dynu.net", "two.org"]
    mock_dns.return_value = None

    response = test_client.post(
        "/subdomains/add",
        data={"subdomain": "cliente", "root": "two.org"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    mock_dns.assert_awaited_once_with(mock_get_settings.return_value, "cliente", "two.org")
    created = mock_db.add.call_args_list[0].args[0]
    assert created.base_domain == "two.org"

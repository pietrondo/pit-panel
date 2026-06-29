from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from pit_panel.db.models import Subdomain, User
from pit_panel.web.routes.apps import app_analyze_repo, app_deploy, apps_list


@pytest.mark.asyncio
async def test_apps_list_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.list_templates.return_value = ["test-template"]
    mock_mgr.return_value.get_template_info.return_value = {"display_name": "Test Template"}
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await apps_list(mock_request, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["user"] == user
    assert kwargs["subdomains"] == []
    assert kwargs["templates"] == ["test-template"]
    assert kwargs["template_infos"] == [
        {"name": "test-template", "meta": {"display_name": "Test Template"}}
    ]


@pytest.mark.asyncio
async def test_app_analyze_repo_unauth(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_analyze_repo(mock_request, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert response.body == b""


@pytest.mark.asyncio
async def test_app_analyze_repo_empty_url(monkeypatch):
    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"repo_url": "   "})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_analyze_repo(mock_request, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert b"Inserisci un URL GitHub" in response.body


@pytest.mark.asyncio
async def test_app_analyze_repo_valueerror(monkeypatch):
    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"repo_url": "invalid"})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    monkeypatch.setattr(
        "pit_panel.web.routes.apps.analyze_repo", AsyncMock(side_effect=ValueError("Invalid repo"))
    )

    response = await app_analyze_repo(mock_request, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert b"Invalid repo" in response.body


@pytest.mark.asyncio
async def test_app_analyze_repo_exception(monkeypatch):
    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"repo_url": "http://github.com/a/b"})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    monkeypatch.setattr(
        "pit_panel.web.routes.apps.analyze_repo", AsyncMock(side_effect=Exception("API error"))
    )

    response = await app_analyze_repo(mock_request, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert b"Errore: API error" in response.body


@pytest.mark.asyncio
async def test_app_analyze_repo_success(monkeypatch):
    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"repo_url": "http://github.com/a/b"})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    class MockDetected:
        stack_type = "nodejs"
        display_name = "NodeJS"
        confidence = 95
        indicators = ["package.json"]

    monkeypatch.setattr(
        "pit_panel.web.routes.apps.analyze_repo", AsyncMock(return_value=MockDetected())
    )

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_mgr = MagicMock()
    mock_mgr.return_value.list_templates.return_value = ["nodejs"]
    mock_mgr.return_value.get_template_info.return_value = {
        "display_name": "Node App",
        "icon": "N",
        "default_port": 3000,
    }
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    response = await app_analyze_repo(mock_request, db=mock_db)

    assert isinstance(response, HTMLResponse)
    body = response.body.decode()
    assert "Node App" in body
    assert "95%" in body
    assert "badge-green" in body
    assert "package.json" in body
    assert "Deploy Automatico" in body


@pytest.mark.asyncio
async def test_app_analyze_repo_success_low_confidence(monkeypatch):
    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"repo_url": "http://github.com/a/b"})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    class MockDetected:
        stack_type = "unknown"
        display_name = "Unknown"
        confidence = 40
        indicators = []

    monkeypatch.setattr(
        "pit_panel.web.routes.apps.analyze_repo", AsyncMock(return_value=MockDetected())
    )

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_mgr = MagicMock()
    mock_mgr.return_value.list_templates.return_value = []
    mock_mgr.return_value.get_template_info.return_value = {}
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    response = await app_analyze_repo(mock_request, db=mock_db)

    assert isinstance(response, HTMLResponse)
    body = response.body.decode()
    assert "badge-red" in body
    assert "Deploy Manuale" in body


@pytest.mark.asyncio
async def test_app_deploy_unauth(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_app_deploy_no_subdomain(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert mock_render.call_args[1]["error"] == "Subdomain not found"


@pytest.mark.asyncio
async def test_app_deploy_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="old_node")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    mock_caddy.return_value.add_main_domain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    response = await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_mgr.return_value.deploy_template.assert_called_once_with(
        "test", "node", variables={"PORT": "3000"}
    )
    mock_caddy.return_value.add_subdomain.assert_called_once_with("test", "example.com")

    assert sd.app_type == "node"
    mock_db.commit.assert_called()
    mock_db.add.assert_called()  # AppDeployment log


@pytest.mark.asyncio
async def test_app_deploy_exception(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd

    mock_list_result = MagicMock()
    mock_list_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result, mock_list_result]

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock(side_effect=ValueError("deploy failed"))
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "deploy failed" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_from_repo_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_deploy_from_repo_no_base_domain(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = ""
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, HTMLResponse)
    assert b"Base domain not configured" in response.body


@pytest.mark.asyncio
async def test_app_deploy_from_repo_success(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    # 1st execute -> no existing subdomain
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com/my_repo", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_mgr.return_value.deploy_template.assert_called_once_with(
        "my-repo", "node", variables={"PORT": "3000"}
    )
    mock_caddy.return_value.add_subdomain.assert_called_once_with("my-repo", "example.com")

    # db.add called twice (Subdomain, AppDeployment, AuditLog) -> wait, 3 times
    assert mock_db.add.call_count == 3
    # no commit on restart


@pytest.mark.asyncio
async def test_app_deploy_from_repo_collision_and_deploy_fail(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    # 1st execute -> collision
    sd = Subdomain(id=1, subdomain="my-repo")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock(side_effect=ValueError("Deploy failed"))
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com/my_repo", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, HTMLResponse)
    assert b"Deploy failed" in response.body


@pytest.mark.asyncio
async def test_app_detail_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_detail

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_detail(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_detail_not_found(monkeypatch):
    from pit_panel.web.routes.apps import app_detail

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await app_detail(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "/apps"


@pytest.mark.asyncio
async def test_app_detail_success(monkeypatch):
    from pit_panel.web.routes.apps import app_detail

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="wordpress")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.compose_ps = AsyncMock(return_value=[{"Name": "test-c"}])
    mock_docker.return_value.compose_logs = AsyncMock(return_value="logs")
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_mgr = MagicMock()
    mock_mgr.return_value.get_template_info.return_value = {"info": "yes"}
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    monkeypatch.setattr("pit_panel.web.routes.apps._get_db_password", lambda s, d: "secret")
    monkeypatch.setattr("pit_panel.web.routes.apps._has_db_container", lambda s, d: True)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_detail(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["sd"] == sd
    assert kwargs["containers"] == [{"Name": "test-c"}]
    assert kwargs["logs"] == "logs"
    assert kwargs["app_info"] == {"info": "yes"}
    assert kwargs["db_password"] == "secret"
    assert kwargs["db_container"] is True


@pytest.mark.asyncio
async def test_app_detail_docker_error(monkeypatch):
    from pit_panel.web.routes.apps import app_detail

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.compose_ps = AsyncMock(side_effect=Exception("ps error"))
    mock_docker.return_value.compose_logs = AsyncMock(side_effect=Exception("logs error"))
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_mgr = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    monkeypatch.setattr("pit_panel.web.routes.apps._has_db_container", lambda s, d: False)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_detail(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["containers"] == []
    assert kwargs["logs"] == "Error fetching logs"


@pytest.mark.asyncio
async def test_app_restart_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_restart

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_restart(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_restart_success(monkeypatch):
    from pit_panel.web.routes.apps import app_restart

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="node")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    response = await app_restart(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_docker.return_value.run_compose_command.assert_called_once_with("test", ["restart"])
    # no audit log on restart
    # no commit on restart


@pytest.mark.asyncio
async def test_app_stop_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_stop

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_stop(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_stop_success(monkeypatch):
    from pit_panel.web.routes.apps import app_stop

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="node")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    response = await app_stop(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_docker.return_value.run_compose_command.assert_called_once_with("test", ["down"])
    mock_db.add.assert_called_once()  # AuditLog
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_app_delete_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_delete

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_delete_success(monkeypatch):
    from pit_panel.web.routes.apps import app_delete

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(
        id=1, subdomain="test", base_domain="example.com", app_type="node", is_main_domain=False
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.remove_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    mock_mgr = MagicMock()
    mock_mgr.return_value.delete_app = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    response = await app_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_docker.return_value.run_compose_command.assert_called_once_with("test", ["down", "-v"])
    mock_caddy.return_value.remove_subdomain.assert_called_once_with("test", "example.com")
    mock_mgr.return_value.delete_app.assert_called_once_with("test")

    assert sd.app_type is None
    mock_db.add.assert_called_once()  # AuditLog
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_app_delete_success_main_domain_and_caddy_error(monkeypatch):
    from pit_panel.web.routes.apps import app_delete

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(
        id=1, subdomain="_main_", base_domain="example.com", app_type="node", is_main_domain=True
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.remove_main_domain = AsyncMock(side_effect=Exception("caddy err"))
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    mock_mgr = MagicMock()
    mock_mgr.return_value.delete_app = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    response = await app_delete(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302

    mock_caddy.return_value.remove_main_domain.assert_called_once_with("example.com")


@pytest.mark.asyncio
async def test_app_containers_get_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_containers_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_containers_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert response.headers["HX-Redirect"] == "/login"


@pytest.mark.asyncio
async def test_app_containers_get_not_found(monkeypatch):
    from pit_panel.web.routes.apps import app_containers_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await app_containers_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert b"App not found" in response.body


@pytest.mark.asyncio
async def test_app_containers_get_success(monkeypatch):
    from pit_panel.web.routes.apps import app_containers_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com", app_type="node")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.compose_ps = AsyncMock(return_value=[{"Name": "c1"}])
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_containers_get(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["sd"] == sd
    assert kwargs["containers"] == [{"Name": "c1"}]


@pytest.mark.asyncio
async def test_app_backup_get_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_backup_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_backup_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert response.headers["HX-Redirect"] == "/login"


@pytest.mark.asyncio
async def test_app_backup_get_not_found(monkeypatch):
    from pit_panel.web.routes.apps import app_backup_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await app_backup_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert b"App not found" in response.body


@pytest.mark.asyncio
async def test_app_backup_get_success(monkeypatch):
    from pit_panel.web.routes.apps import app_backup_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_backup_get(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["sd"] == sd


@pytest.mark.asyncio
async def test_app_logs_get_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_logs_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_logs_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert response.headers["HX-Redirect"] == "/login"


@pytest.mark.asyncio
async def test_app_logs_get_not_found(monkeypatch):
    from pit_panel.web.routes.apps import app_logs_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await app_logs_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert b"App not found" in response.body


@pytest.mark.asyncio
async def test_app_logs_get_success(monkeypatch):
    from pit_panel.web.routes.apps import app_logs_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.compose_logs = AsyncMock(return_value="logs output")
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_logs_get(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["sd"] == sd
    assert kwargs["logs"] == "logs output"


@pytest.mark.asyncio
async def test_app_logs_get_exception(monkeypatch):
    from pit_panel.web.routes.apps import app_logs_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_docker = MagicMock()
    mock_docker.return_value.compose_logs = AsyncMock(side_effect=Exception("error"))
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_logs_get(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["logs"] == "Error fetching logs"


@pytest.mark.asyncio
async def test_app_env_get_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_env_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_env_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_env_get_not_found(monkeypatch):
    from pit_panel.web.routes.apps import app_env_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await app_env_get(mock_request, sd_id=1, db=mock_db)

    assert isinstance(response, str)
    assert "App not found" in response


@pytest.mark.asyncio
async def test_app_env_get_no_file(monkeypatch):
    from pit_panel.web.routes.apps import app_env_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    import os

    monkeypatch.setattr(os.path, "exists", lambda x: False)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_env_get(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["env_content"] == "# No .env file found"


@pytest.mark.asyncio
async def test_app_env_get_success(monkeypatch, tmp_path):
    from pit_panel.web.routes.apps import app_env_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    app_dir = tmp_path / "test"
    app_dir.mkdir()
    env_file = app_dir / ".env"
    env_file.write_text("FOO=bar")

    mock_settings = MagicMock()
    mock_settings.apps_dir = str(tmp_path)
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_env_get(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["env_content"] == "FOO=bar"


@pytest.mark.asyncio
async def test_app_env_get_exception(monkeypatch):
    from pit_panel.web.routes.apps import app_env_get

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    import os

    monkeypatch.setattr(os.path, "exists", lambda x: True)

    def mock_open(*args, **kwargs):
        raise Exception("error")

    import builtins

    monkeypatch.setattr(builtins, "open", mock_open)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_env_get(mock_request, sd_id=1, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["env_content"] == "# Error reading .env file"


@pytest.mark.asyncio
async def test_app_env_post_unauth(monkeypatch):
    from pit_panel.web.routes.apps import app_env_post

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await app_env_post(mock_request, sd_id=1, env_content="FOO=bar", db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_env_post_not_found(monkeypatch):
    from pit_panel.web.routes.apps import app_env_post

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await app_env_post(mock_request, sd_id=1, env_content="FOO=bar", db=mock_db)

    assert isinstance(response, str)
    assert "App not found" in response


@pytest.mark.asyncio
async def test_app_env_post_quotes(monkeypatch):
    from pit_panel.web.routes.apps import app_env_post

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    response = await app_env_post(mock_request, sd_id=1, env_content='FOO="bar"', db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 400
    assert b"Quotes are not allowed" in response.body


@pytest.mark.asyncio
async def test_app_env_post_success(monkeypatch, tmp_path):
    from pit_panel.web.routes.apps import app_env_post

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    app_dir = tmp_path / "test"
    app_dir.mkdir()

    mock_settings = MagicMock()
    mock_settings.apps_dir = str(tmp_path)
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_env_post(mock_request, sd_id=1, env_content="FOO=bar", db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["env_content"] == "FOO=bar"
    assert "updated successfully" in kwargs["success"]
    assert mock_db.commit.called
    assert mock_db.add.called

    # check file
    env_file = app_dir / ".env"
    assert env_file.read_text() == "FOO=bar"


@pytest.mark.asyncio
async def test_app_env_post_exception(monkeypatch):
    from pit_panel.web.routes.apps import app_env_post

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    def mock_open(*args, **kwargs):
        raise Exception("error")

    import builtins

    monkeypatch.setattr(builtins, "open", mock_open)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_env_post(mock_request, sd_id=1, env_content="FOO=bar", db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert "Error saving" in kwargs["error"]


@pytest.mark.asyncio
async def test_app_wp_endpoints_unauth(monkeypatch):
    from pit_panel.web.routes.apps import (
        app_wp_flush_cache,
        app_wp_update_core,
        app_wp_update_plugins,
    )

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    for fn in (app_wp_flush_cache, app_wp_update_plugins, app_wp_update_core):
        response = await fn(mock_request, sd_id=1, db=mock_db)
        assert isinstance(response, HTMLResponse)
        assert response.headers["HX-Redirect"] == "/login"


@pytest.mark.asyncio
async def test_app_wp_endpoints_not_found(monkeypatch):
    from pit_panel.web.routes.apps import (
        app_wp_flush_cache,
        app_wp_update_core,
        app_wp_update_plugins,
    )

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    for fn in (app_wp_flush_cache, app_wp_update_plugins, app_wp_update_core):
        response = await fn(mock_request, sd_id=1, db=mock_db)
        assert isinstance(response, HTMLResponse)
        assert b"App not found" in response.body


@pytest.mark.asyncio
async def test_app_wp_endpoints_success(monkeypatch):
    import asyncio

    from pit_panel.web.routes.apps import (
        app_wp_flush_cache,
        app_wp_update_core,
        app_wp_update_plugins,
    )

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"out", b"err"))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    res1 = await app_wp_flush_cache(mock_request, sd_id=1, db=mock_db)
    assert b"successfully" in res1.body

    res2 = await app_wp_update_plugins(mock_request, sd_id=1, db=mock_db)
    assert b"successfully" in res2.body

    res3 = await app_wp_update_core(mock_request, sd_id=1, db=mock_db)
    assert b"successfully" in res3.body


@pytest.mark.asyncio
async def test_app_wp_endpoints_error(monkeypatch):
    import asyncio

    from pit_panel.web.routes.apps import (
        app_wp_flush_cache,
        app_wp_update_core,
        app_wp_update_plugins,
    )

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"out", b"wp err"))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    res1 = await app_wp_flush_cache(mock_request, sd_id=1, db=mock_db)
    assert b"Error: wp err" in res1.body

    res2 = await app_wp_update_plugins(mock_request, sd_id=1, db=mock_db)
    assert b"Error: wp err" in res2.body

    res3 = await app_wp_update_core(mock_request, sd_id=1, db=mock_db)
    assert b"Error: wp err" in res3.body


@pytest.mark.asyncio
async def test_app_wp_endpoints_exception(monkeypatch):
    import asyncio

    from pit_panel.web.routes.apps import (
        app_wp_flush_cache,
        app_wp_update_core,
        app_wp_update_plugins,
    )

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(side_effect=Exception("create err"))
    )

    res1 = await app_wp_flush_cache(mock_request, sd_id=1, db=mock_db)
    assert b"Exception: create err" in res1.body

    res2 = await app_wp_update_plugins(mock_request, sd_id=1, db=mock_db)
    assert b"Exception: create err" in res2.body

    res3 = await app_wp_update_core(mock_request, sd_id=1, db=mock_db)
    assert b"Exception: create err" in res3.body


def test_get_db_password(tmp_path, monkeypatch):
    from pit_panel.web.routes.apps import _get_db_password

    mock_settings = MagicMock()
    mock_settings.apps_dir = str(tmp_path)

    app_dir = tmp_path / "test"
    app_dir.mkdir()
    env_file = app_dir / ".env"

    env_file.write_text("DB_PASSWORD=secret")
    assert _get_db_password(mock_settings, "test") == "secret"

    env_file.write_text("WORDPRESS_DB_PASSWORD='wp_secret'")
    assert _get_db_password(mock_settings, "test") == "wp_secret"

    env_file.write_text("OTHER=foo")
    assert _get_db_password(mock_settings, "test") is None

    # Exception case
    env_file.unlink()
    assert _get_db_password(mock_settings, "test") is None


def test_has_db_container(tmp_path):
    from pit_panel.web.routes.apps import _has_db_container

    mock_settings = MagicMock()
    mock_settings.apps_dir = str(tmp_path)

    app_dir = tmp_path / "test"
    app_dir.mkdir()
    yml_file = app_dir / "docker-compose.yml"

    yml_file.write_text("image: mysql:8")
    assert _has_db_container(mock_settings, "test") is True

    yml_file.write_text("image: mariadb")
    assert _has_db_container(mock_settings, "test") is True

    yml_file.write_text("image: postgres")
    assert _has_db_container(mock_settings, "test") is True

    yml_file.write_text("image: nginx")
    assert _has_db_container(mock_settings, "test") is False

    # Exception case
    yml_file.unlink()
    assert _has_db_container(mock_settings, "test") is False


@pytest.mark.asyncio
async def test_app_deploy_main_domain_no_base(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = ""
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_list_result = MagicMock()
    mock_list_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_list_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=True,
        subdomain_id=-1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "Base domain not configured" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_main_domain_existing_deployed(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    sd = Subdomain(id=1, subdomain="_main_", app_type="node", is_main_domain=True)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd

    mock_list_result = MagicMock()
    mock_list_result.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [mock_result, mock_list_result]

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=True,
        subdomain_id=-1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "already deployed" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_main_domain_new(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_main_domain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    res = await app_deploy(
        mock_request,
        is_main_domain=True,
        subdomain_id=-1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    assert isinstance(res, RedirectResponse)
    mock_caddy.return_value.add_main_domain.assert_called_once()


@pytest.mark.asyncio
async def test_app_deploy_new_subdomain_invalid(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_list_result = MagicMock()
    mock_list_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_list_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=-1,
        new_subdomain="invalid!",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "Invalid subdomain" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_new_subdomain_no_base_domain(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = ""
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_list_result = MagicMock()
    mock_list_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_list_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=-1,
        new_subdomain="valid",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "Base domain not configured" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_new_subdomain_success(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    res = await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=-1,
        new_subdomain="valid",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    assert isinstance(res, RedirectResponse)
    mock_caddy.return_value.add_subdomain.assert_called_once()


@pytest.mark.asyncio
async def test_app_deploy_no_input(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_list_result = MagicMock()
    mock_list_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_list_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=-1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "Select an existing subdomain" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_compose_fail(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(
        return_value={"success": False, "stderr": "compose err"}
    )
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "compose err" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_compose_exception(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(
        side_effect=Exception("compose exec fail")
    )
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "compose exec fail" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_caddy_exception(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    sd = Subdomain(id=1, subdomain="test", base_domain="example.com")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock(side_effect=Exception("caddy failure"))
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.render", mock_render)

    await app_deploy(
        mock_request,
        is_main_domain=False,
        subdomain_id=1,
        new_subdomain="",
        stack_type="node",
        port=3000,
        db=mock_db,
    )

    mock_render.assert_called_once()
    assert "caddy failure" in mock_render.call_args[1]["error"]


@pytest.mark.asyncio
async def test_app_deploy_from_repo_fallback_name(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    # 1st execute -> no existing subdomain
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    # Empty repo url to trigger fallback name
    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com/", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, RedirectResponse)

    mock_caddy.return_value.add_subdomain.assert_called_once_with("gitcom", "example.com")


@pytest.mark.asyncio
async def test_app_deploy_from_repo_compose_exception(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(side_effect=Exception("compose error"))
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com/repo", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    # verify compose_ok was False by checking AppDeployment status
    added_deployment = [
        call[0][0]
        for call in mock_db.add.call_args_list
        if type(call[0][0]).__name__ == "AppDeployment"
    ][0]
    assert added_deployment.status == "failed"


@pytest.mark.asyncio
async def test_app_deploy_from_repo_caddy_exception(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock(side_effect=Exception("caddy error"))
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com/repo", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, RedirectResponse)


@pytest.mark.asyncio
async def test_apps_list_unauth_redirect(monkeypatch):
    from pit_panel.web.routes.apps import apps_list

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    response = await apps_list(mock_request, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_app_deploy_from_repo_fallback_name_empty(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    # 1st execute -> no existing subdomain
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    # Empty repo url to trigger fallback name completely empty after regex
    response = await app_deploy_from_repo(
        mock_request, repo_url="http://git.com/___", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, RedirectResponse)

    mock_caddy.return_value.add_subdomain.assert_called_once_with("---", "example.com")


@pytest.mark.asyncio
async def test_app_deploy_from_repo_fallback_name_empty_2(monkeypatch):
    from pit_panel.web.routes.apps import app_deploy_from_repo

    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"
    mock_request.headers.get.return_value = "TestAgent"
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")
    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", AsyncMock(return_value=user))

    mock_settings = MagicMock()
    mock_settings.base_domain = "example.com"
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: mock_settings)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.return_value.deploy_template = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.AppManager", mock_mgr)

    mock_docker = MagicMock()
    mock_docker.return_value.run_compose_command = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("pit_panel.web.routes.apps.DockerManager", mock_docker)

    mock_caddy = MagicMock()
    mock_caddy.return_value.add_subdomain = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.apps.CaddyManager", mock_caddy)

    # Completely invalid url resulting in empty name
    response = await app_deploy_from_repo(
        mock_request, repo_url="!@#$%^&*", stack_type="node", port=3000, db=mock_db
    )

    assert isinstance(response, RedirectResponse)
    mock_caddy.return_value.add_subdomain.assert_called_once_with("app", "example.com")

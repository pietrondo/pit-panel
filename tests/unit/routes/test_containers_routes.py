from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from pit_panel.db.models import Subdomain, User
from pit_panel.web.routes.containers import (
    container_logs,
    container_logs_live,
    container_restart,
    container_start,
    container_stats,
    container_stop,
    containers_fragment,
    containers_list,
)


@pytest.mark.asyncio
async def test_containers_fragment_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await containers_fragment(mock_request, db=mock_db)

    assert isinstance(response, HTMLResponse)
    assert response.headers["HX-Redirect"] == "/login"


@pytest.mark.asyncio
async def test_containers_fragment_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.ps_all = AsyncMock(
        return_value=[
            {"Names": "c1", "Labels": "com.docker.compose.project=app1"},
            {"Name": "c2", "Labels": "com.docker.compose.project=app2"},
            {"Name": "c3", "Labels": ""},
        ]
    )
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    sd1 = Subdomain(id=1, subdomain="app1")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sd1]
    mock_db.execute.return_value = mock_result

    mock_render = MagicMock()
    mock_render.return_value.body = b"fragment content"
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    res = await containers_fragment(mock_request, db=mock_db)

    assert isinstance(res, HTMLResponse)
    assert b"fragment content" in res.body

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert len(kwargs["orphan_containers"]) == 2  # c2 (app2 not in subdomains) and c3 (no labels)
    assert len(kwargs["containers_data"]) == 1


@pytest.mark.asyncio
async def test_containers_list_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await containers_list(mock_request, db=mock_db)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_containers_list_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.ps_all = AsyncMock(
        return_value=[{"Names": "c1", "Labels": "com.docker.compose.project=app1"}]
    )
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    sd1 = Subdomain(id=1, subdomain="app1")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sd1]
    mock_db.execute.return_value = mock_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await containers_list(mock_request, db=mock_db)
    mock_render.assert_called_once()


@pytest.mark.asyncio
async def test_containers_list_authenticated_orphan(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.ps_all = AsyncMock(return_value=[{"Names": "c1"}])
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await containers_list(mock_request, db=mock_db)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert len(kwargs["orphan_containers"]) == 1


@pytest.mark.asyncio
async def test_container_logs_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await container_logs(mock_request, sd_id=1, db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_container_logs_not_found(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await container_logs(mock_request, sd_id=1, db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == "/containers"


@pytest.mark.asyncio
async def test_container_logs_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    sd1 = Subdomain(id=1, subdomain="app1")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd1
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.compose_logs = AsyncMock(return_value="logs")
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await container_logs(mock_request, sd_id=1, db=mock_db)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["logs"] == "logs"


@pytest.mark.asyncio
async def test_container_logs_exception(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    sd1 = Subdomain(id=1, subdomain="app1")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd1
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.compose_logs = AsyncMock(side_effect=Exception("failed"))
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await container_logs(mock_request, sd_id=1, db=mock_db)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["logs"] == "Error fetching logs"


@pytest.mark.asyncio
async def test_container_restart_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await container_restart(mock_request, sd_id=1, db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_container_restart_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    sd1 = Subdomain(id=1, subdomain="app1")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sd1
    mock_db.execute.return_value = mock_result

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.run_compose_command = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    response = await container_restart(mock_request, sd_id=1, db=mock_db)
    assert isinstance(response, RedirectResponse)
    mock_docker_mgr.return_value.run_compose_command.assert_called_once_with("app1", ["restart"])


@pytest.mark.asyncio
async def test_container_restart_not_found(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    response = await container_restart(mock_request, sd_id=1, db=mock_db)
    assert isinstance(response, RedirectResponse)


@pytest.mark.asyncio
async def test_container_stop_invalid_id():

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    response = await container_stop(mock_request, container_id="invalid!id", db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_container_stop_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await container_stop(mock_request, container_id="valid_id", db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_container_stop_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.container_stop = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    response = await container_stop(mock_request, container_id="valid_id", db=mock_db)
    assert isinstance(response, RedirectResponse)
    mock_docker_mgr.return_value.container_stop.assert_called_once_with("valid_id")


@pytest.mark.asyncio
async def test_container_start_invalid_id():

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    response = await container_start(mock_request, container_id="invalid!id", db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_container_start_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await container_start(mock_request, container_id="valid_id", db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_container_start_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.container_start = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    response = await container_start(mock_request, container_id="valid_id", db=mock_db)
    assert isinstance(response, RedirectResponse)
    mock_docker_mgr.return_value.container_start.assert_called_once_with("valid_id")


@pytest.mark.asyncio
async def test_container_logs_live_invalid_id():

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    response = await container_logs_live(mock_request, container_id="invalid!id", db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_container_logs_live_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await container_logs_live(mock_request, container_id="valid_id", db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_container_logs_live_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.container_logs_live = AsyncMock(return_value="live logs")
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await container_logs_live(mock_request, container_id="valid_id", db=mock_db)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["logs"] == "live logs"


@pytest.mark.asyncio
async def test_container_logs_live_exception(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.container_logs_live = AsyncMock(side_effect=Exception("error"))
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await container_logs_live(mock_request, container_id="valid_id", db=mock_db)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["logs"] == "Error fetching logs"


@pytest.mark.asyncio
async def test_container_stats_invalid_id():

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    response = await container_stats(mock_request, container_id="invalid!id", db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_container_stats_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_user(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    response = await container_stats(mock_request, container_id="valid_id", db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_container_stats_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.container_stats = AsyncMock(return_value={"cpu": "10%"})
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await container_stats(mock_request, container_id="valid_id", db=mock_db)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["stats"] == {"cpu": "10%"}


@pytest.mark.asyncio
async def test_container_stats_exception(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin")

    async def mock_get_user(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.get_settings", lambda: mock_settings)

    mock_docker_mgr = MagicMock()
    mock_docker_mgr.return_value.container_stats = AsyncMock(side_effect=Exception("failed"))
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", mock_docker_mgr)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.containers.render", mock_render)

    await container_stats(mock_request, container_id="valid_id", db=mock_db)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["stats"] == {}

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import HTMLResponse
from httpx import ASGITransport, AsyncClient

from pit_panel.db.models import User
from pit_panel.web.app import create_app


@pytest.fixture
def mock_user():
    user = User(id=1, username="admin", email="admin@example.com")
    return user

@pytest.fixture
def app():
    return create_app()

@pytest.fixture
def transport(app):
    return ASGITransport(app=app)

@pytest.fixture
def app_with_overrides(app):
    from pit_panel.db.session import get_db
    async def override_get_db():
        yield AsyncMock()
    app.dependency_overrides[get_db] = override_get_db
    return app

@pytest.fixture
def transport_overrides(app_with_overrides):
    return ASGITransport(app=app_with_overrides)

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock, return_value=None)
async def test_containers_fragment_unauthenticated(mock_get_user, transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/fragment", headers={"hx-request": "true"})
            assert response.status_code == 200
            assert response.headers.get("HX-Redirect") == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers._get_containers_data", new_callable=AsyncMock)
async def test_containers_fragment_authenticated(mock_get_data, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_get_data.return_value = ({}, {}, [])

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Rendered</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers/fragment")
                assert response.status_code == 200
                assert "hx-get=\"/containers/fragment\"" in response.text
                assert "<div>Rendered</div>" in response.text

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers._get_containers_data", new_callable=AsyncMock)
async def test_containers_list_authenticated(mock_get_data, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_get_data.return_value = ({}, {}, [])

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Rendered List</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers")
                assert response.status_code == 200
                assert "<div>Rendered List</div>" in response.text

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock, return_value=None)
async def test_containers_list_unauthenticated(mock_get_user, transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock, return_value=None)
async def test_containers_list_unauthenticated_hx(mock_get_user, transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers", headers={"hx-request": "true"})
            assert response.status_code == 200
            assert response.headers.get("HX-Redirect") == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock, return_value=None)
async def test_container_logs_unauthenticated(mock_get_user, transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/1/logs")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock, return_value=None)
async def test_container_logs_unauthenticated_hx(mock_get_user, transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/1/logs", headers={"hx-request": "true"})
            assert response.status_code == 200
            assert response.headers.get("HX-Redirect") == "/login"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
async def test_container_logs_authenticated_not_found(mock_get_user, transport_overrides, mock_user, app_with_overrides):
    mock_get_user.return_value = mock_user

    # Mock the database execute call to return none
    mock_db = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = lambda: None
    mock_db.execute.return_value = mock_result

    # Override dependency
    from pit_panel.db.session import get_db
    async def override_get_db():
        yield mock_db
    app_with_overrides.dependency_overrides[get_db] = override_get_db

    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/1/logs")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/containers"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_logs_authenticated_found(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user, app_with_overrides):
    mock_get_user.return_value = mock_user

    from pit_panel.db.models import Subdomain
    mock_sd = Subdomain(id=1, subdomain="test", app_type="docker")

    mock_db = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = lambda: mock_sd
    mock_db.execute.return_value = mock_result

    # Override dependency
    from pit_panel.db.session import get_db
    async def override_get_db():
        yield mock_db
    app_with_overrides.dependency_overrides[get_db] = override_get_db

    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.compose_logs = AsyncMock(return_value="Some logs")

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Logs Rendered</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers/1/logs")
                assert response.status_code == 200
                assert "<div>Logs Rendered</div>" in response.text
                mock_docker_mgr.compose_logs.assert_called_once_with("test", tail=200)

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_logs_authenticated_found_error(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user, app_with_overrides):
    mock_get_user.return_value = mock_user

    from pit_panel.db.models import Subdomain
    mock_sd = Subdomain(id=1, subdomain="test", app_type="docker")

    mock_db = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = lambda: mock_sd
    mock_db.execute.return_value = mock_result

    # Override dependency
    from pit_panel.db.session import get_db
    async def override_get_db():
        yield mock_db
    app_with_overrides.dependency_overrides[get_db] = override_get_db

    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.compose_logs = AsyncMock(side_effect=Exception("Error"))

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Logs Rendered</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers/1/logs")
                assert response.status_code == 200
                assert "<div>Logs Rendered</div>" in response.text
                mock_docker_mgr.compose_logs.assert_called_once_with("test", tail=200)

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock, return_value=None)
async def test_container_restart_unauthenticated(mock_get_user, transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/1/restart")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock, return_value=None)
async def test_container_restart_unauthenticated_hx(mock_get_user, transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/1/restart", headers={"hx-request": "true"})
            assert response.status_code == 200
            assert response.headers.get("HX-Redirect") == "/login"

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_restart_authenticated_found(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user, app_with_overrides):
    mock_get_user.return_value = mock_user

    from pit_panel.db.models import Subdomain
    mock_sd = Subdomain(id=1, subdomain="test", app_type="docker")

    mock_db = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = lambda: mock_sd
    mock_db.execute.return_value = mock_result

    # Override dependency
    from pit_panel.db.session import get_db
    async def override_get_db():
        yield mock_db
    app_with_overrides.dependency_overrides[get_db] = override_get_db

    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.run_compose_command = AsyncMock()

    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/1/restart")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/containers"
            mock_docker_mgr.run_compose_command.assert_called_once_with("test", ["restart"])

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_stop_authenticated(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.container_stop = AsyncMock()

    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/container/test_container/stop")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/containers"
            mock_docker_mgr.container_stop.assert_called_once_with("test_container")

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
async def test_container_stop_unauthenticated(mock_get_user, transport_overrides):
    mock_get_user.return_value = None
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/container/test_container/stop")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/login"

@pytest.mark.asyncio
async def test_container_stop_invalid_id(transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/container/invalid id!/stop")
            assert response.status_code == 400
            assert "Invalid container ID" in response.text

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_start_authenticated(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.container_start = AsyncMock()

    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/container/test_container/start")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/containers"
            mock_docker_mgr.container_start.assert_called_once_with("test_container")

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
async def test_container_start_unauthenticated(mock_get_user, transport_overrides):
    mock_get_user.return_value = None
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/container/test_container/start")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/login"

@pytest.mark.asyncio
async def test_container_start_invalid_id(transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.post("/containers/container/invalid id!/start")
            assert response.status_code == 400
            assert "Invalid container ID" in response.text

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_logs_live_authenticated(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.container_logs_live = AsyncMock(return_value="Live logs")

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Live Logs Rendered</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers/container/test_container/logs")
                assert response.status_code == 200
                assert "<div>Live Logs Rendered</div>" in response.text
                mock_docker_mgr.container_logs_live.assert_called_once_with("test_container", tail=200)

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_logs_live_authenticated_error(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.container_logs_live = AsyncMock(side_effect=Exception("Error"))

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Error Logs Rendered</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers/container/test_container/logs")
                assert response.status_code == 200
                assert "<div>Error Logs Rendered</div>" in response.text
                mock_docker_mgr.container_logs_live.assert_called_once_with("test_container", tail=200)

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
async def test_container_logs_live_unauthenticated(mock_get_user, transport_overrides):
    mock_get_user.return_value = None
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/container/test_container/logs")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/login"

@pytest.mark.asyncio
async def test_container_logs_live_invalid_id(transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/container/invalid id!/logs")
            assert response.status_code == 400
            assert "Invalid container ID" in response.text

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_stats_authenticated(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.container_stats = AsyncMock(return_value={"cpu": "10%"})

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Stats Rendered</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers/container/test_container/stats")
                assert response.status_code == 200
                assert "<div>Stats Rendered</div>" in response.text
                mock_docker_mgr.container_stats.assert_called_once_with("test_container")

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
@patch("pit_panel.web.routes.containers.DockerManager")
async def test_container_stats_authenticated_error(mock_docker_mgr_cls, mock_get_user, transport_overrides, mock_user):
    mock_get_user.return_value = mock_user
    mock_docker_mgr = mock_docker_mgr_cls.return_value
    mock_docker_mgr.container_stats = AsyncMock(side_effect=Exception("Error"))

    with patch("pit_panel.web.routes.containers.render") as mock_render:
        mock_render.return_value = HTMLResponse(b"<div>Stats Rendered</div>")
        with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
                response = await client.get("/containers/container/test_container/stats")
                assert response.status_code == 200
                assert "<div>Stats Rendered</div>" in response.text
                mock_docker_mgr.container_stats.assert_called_once_with("test_container")

@pytest.mark.asyncio
@patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock)
async def test_container_stats_unauthenticated(mock_get_user, transport_overrides):
    mock_get_user.return_value = None
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/container/test_container/stats")
            assert response.status_code == 302
            assert response.headers.get("Location") == "/login"

@pytest.mark.asyncio
async def test_container_stats_invalid_id(transport_overrides):
    with patch("pit_panel.web.app.is_ip_banned", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=transport_overrides, base_url="http://testserver") as client:
            response = await client.get("/containers/container/invalid id!/stats")
            assert response.status_code == 400
            assert "Invalid container ID" in response.text


@pytest.mark.asyncio
async def test_get_containers_data():
    from pit_panel.db.models import Subdomain
    from pit_panel.web.routes.containers import _get_containers_data

    sd1 = Subdomain(id=1, subdomain="test1", app_type="docker")
    sd2 = Subdomain(id=2, subdomain="test2", app_type="docker")

    class MockScalars:
        def all(self):
            return [sd1, sd2]

    class MockResult:
        def scalars(self):
            return MockScalars()

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MockResult())

    mock_docker_mgr = AsyncMock()

    container1 = {
        "Name": "container1",
        "Labels": "com.docker.compose.project=test1, other_label=value"
    }
    container2 = {
        "Names": "container2",
        "Labels": "com.docker.compose.project=test2"
    }
    container3 = {
        "Name": "container3",
        "Labels": "some_other_label=value"
    }
    container4 = {
        "Name": "container4"
    }

    mock_docker_mgr.ps_all.return_value = [container1, container2, container3, container4]

    subdomains, containers_data, orphan_containers = await _get_containers_data(mock_db, mock_docker_mgr)

    assert "test1" in subdomains
    assert "test2" in subdomains
    assert 1 in containers_data
    assert containers_data[1][0]["Name"] == "container1"
    assert 2 in containers_data
    assert containers_data[2][0]["Name"] == "container2"
    assert len(orphan_containers) == 2

@pytest.mark.asyncio
async def test_get_containers_data_exception():
    from pit_panel.web.routes.containers import _get_containers_data

    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB Error")

    mock_docker_mgr = AsyncMock()
    mock_docker_mgr.ps_all.return_value = []

    with pytest.raises(Exception):
        await _get_containers_data(mock_db, mock_docker_mgr)


@pytest.mark.asyncio
async def test_get_containers_data_exception_cancel():
    import asyncio

    from pit_panel.web.routes.containers import _get_containers_data

    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB Error")

    mock_docker_mgr = AsyncMock()

    async def delayed_ps_all():
        await asyncio.sleep(0.1)
        return []

    mock_docker_mgr.ps_all = delayed_ps_all

    with pytest.raises(Exception):
        await _get_containers_data(mock_db, mock_docker_mgr)

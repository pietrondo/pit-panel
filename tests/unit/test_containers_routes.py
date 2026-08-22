import unittest.mock
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse

from pit_panel.web.routes.containers import router as containers_router
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.db.models import Subdomain


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(containers_router)
    return app


@pytest.fixture
def mock_db():
    db = AsyncMock()
    # By default return nothing
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    return db


@pytest.fixture
def mock_user():
    return MagicMock(id=1, username="admin")


@pytest.fixture
def client(app, mock_db, mock_user):
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock) as mock:
        mock.return_value = mock_user
        yield TestClient(app)

@pytest.fixture
def unauth_client(app, mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("pit_panel.web.routes.containers.get_user", new_callable=AsyncMock) as mock:
        mock.return_value = None
        yield TestClient(app)


# Mock _get_containers_data globally to avoid slow docker ops
@pytest.fixture(autouse=True)
def mock_get_containers_data():
    with patch("pit_panel.web.routes.containers._get_containers_data", new_callable=AsyncMock) as mock:
        mock.return_value = ({}, {}, [])
        yield mock


@pytest.fixture(autouse=True)
def mock_docker_manager():
    with patch("pit_panel.web.routes.containers.DockerManager") as mock:
        instance = mock.return_value
        instance.compose_logs = AsyncMock(return_value="logs")
        instance.run_compose_command = AsyncMock()
        instance.container_stop = AsyncMock()
        instance.container_start = AsyncMock()
        instance.container_logs_live = AsyncMock(return_value="live logs")
        instance.container_stats = AsyncMock(return_value={"cpu": "1%"})
        yield instance


@pytest.fixture(autouse=True)
def mock_render():
    with patch("pit_panel.web.routes.containers.render") as mock:
        mock.return_value = HTMLResponse("rendered")
        yield mock


# --- tests for /containers/fragment ---

def test_containers_fragment_unauth(unauth_client):
    response = unauth_client.get("/containers/fragment")
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/login"


def test_containers_fragment_auth(client, mock_render):
    mock_render.return_value = MagicMock(body=b"rendered_fragment")
    response = client.get("/containers/fragment")
    assert response.status_code == 200
    assert "containers-list-wrapper" in response.text
    assert "rendered_fragment" in response.text


# --- tests for /containers ---

def test_containers_list_unauth_regular(unauth_client):
    response = unauth_client.get("/containers", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_containers_list_unauth_htmx(unauth_client):
    response = unauth_client.get("/containers", headers={"hx-request": "true"})
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/login"


def test_containers_list_auth(client):
    response = client.get("/containers")
    assert response.status_code == 200
    assert response.text == "rendered"


# --- tests for /containers/{sd_id}/logs ---

def test_container_logs_unauth_regular(unauth_client):
    response = unauth_client.get("/containers/1/logs", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_container_logs_unauth_htmx(unauth_client):
    response = unauth_client.get("/containers/1/logs", headers={"hx-request": "true"})
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/login"


def test_container_logs_auth_not_found(client, mock_db):
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    response = client.get("/containers/1/logs", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/containers"


def test_container_logs_auth_found(client, mock_db, mock_docker_manager, mock_render):
    sd = Subdomain(id=1, subdomain="test")
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=sd))
    response = client.get("/containers/1/logs")
    assert response.status_code == 200
    assert response.text == "rendered"
    mock_docker_manager.compose_logs.assert_called_once_with("test", tail=200)
    mock_render.assert_called_once_with("container_logs.html", user=unittest.mock.ANY, subdomain=sd, logs="logs")

def test_container_logs_auth_found_error(client, mock_db, mock_docker_manager, mock_render):
    sd = Subdomain(id=1, subdomain="test")
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=sd))
    mock_docker_manager.compose_logs.side_effect = Exception("error")
    response = client.get("/containers/1/logs")
    assert response.status_code == 200
    assert response.text == "rendered"
    mock_render.assert_called_once_with("container_logs.html", user=unittest.mock.ANY, subdomain=sd, logs="Error fetching logs")


# --- tests for /containers/{sd_id}/restart ---

def test_container_restart_unauth_regular(unauth_client):
    response = unauth_client.post("/containers/1/restart", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_container_restart_unauth_htmx(unauth_client):
    response = unauth_client.post("/containers/1/restart", headers={"hx-request": "true"})
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/login"


def test_container_restart_auth_not_found(client, mock_db, mock_docker_manager):
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    response = client.post("/containers/1/restart", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/containers"
    mock_docker_manager.run_compose_command.assert_not_called()


def test_container_restart_auth_found(client, mock_db, mock_docker_manager):
    sd = Subdomain(id=1, subdomain="test")
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=sd))
    response = client.post("/containers/1/restart", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/containers"
    mock_docker_manager.run_compose_command.assert_called_once_with("test", ["restart"])


# --- tests for /containers/container/{container_id}/stop ---

def test_container_stop_invalid_id(client):
    response = client.post("/containers/container/invalid id/stop")
    assert response.status_code == 400
    assert response.text == "Invalid container ID"


def test_container_stop_unauth(unauth_client):
    response = unauth_client.post("/containers/container/valid-id/stop", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_container_stop_auth(client, mock_docker_manager):
    response = client.post("/containers/container/valid-id/stop", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/containers"
    mock_docker_manager.container_stop.assert_called_once_with("valid-id")


# --- tests for /containers/container/{container_id}/start ---

def test_container_start_invalid_id(client):
    response = client.post("/containers/container/invalid id/start")
    assert response.status_code == 400
    assert response.text == "Invalid container ID"


def test_container_start_unauth(unauth_client):
    response = unauth_client.post("/containers/container/valid-id/start", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_container_start_auth(client, mock_docker_manager):
    response = client.post("/containers/container/valid-id/start", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/containers"
    mock_docker_manager.container_start.assert_called_once_with("valid-id")


# --- tests for /containers/container/{container_id}/logs ---

def test_container_logs_live_invalid_id(client):
    response = client.get("/containers/container/invalid id/logs")
    assert response.status_code == 400
    assert response.text == "Invalid container ID"


def test_container_logs_live_unauth(unauth_client):
    response = unauth_client.get("/containers/container/valid-id/logs", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_container_logs_live_auth(client, mock_docker_manager, mock_render):
    response = client.get("/containers/container/valid-id/logs")
    assert response.status_code == 200
    assert response.text == "rendered"
    mock_docker_manager.container_logs_live.assert_called_once_with("valid-id", tail=200)
    mock_render.assert_called_once_with("container_logs.html", user=unittest.mock.ANY, logs="live logs", subdomain=None, container_id="valid-id")

def test_container_logs_live_auth_error(client, mock_docker_manager, mock_render):
    mock_docker_manager.container_logs_live.side_effect = Exception("error")
    response = client.get("/containers/container/valid-id/logs")
    assert response.status_code == 200
    assert response.text == "rendered"
    mock_render.assert_called_once_with("container_logs.html", user=unittest.mock.ANY, logs="Error fetching logs", subdomain=None, container_id="valid-id")


# --- tests for /containers/container/{container_id}/stats ---

def test_container_stats_invalid_id(client):
    response = client.get("/containers/container/invalid id/stats")
    assert response.status_code == 400
    assert response.text == "Invalid container ID"


def test_container_stats_unauth(unauth_client):
    response = unauth_client.get("/containers/container/valid-id/stats", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_container_stats_auth(client, mock_docker_manager, mock_render):
    response = client.get("/containers/container/valid-id/stats")
    assert response.status_code == 200
    assert response.text == "rendered"
    mock_docker_manager.container_stats.assert_called_once_with("valid-id")
    mock_render.assert_called_once_with("container_stats.html", stats={"cpu": "1%"}, container_id="valid-id")

def test_container_stats_auth_error(client, mock_docker_manager, mock_render):
    mock_docker_manager.container_stats.side_effect = Exception("error")
    response = client.get("/containers/container/valid-id/stats")
    assert response.status_code == 200
    assert response.text == "rendered"
    mock_render.assert_called_once_with("container_stats.html", stats={}, container_id="valid-id")

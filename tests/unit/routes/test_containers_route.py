import asyncio
import re
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Base, Subdomain, User
from pit_panel.web.app import create_app
from pit_panel.web.routes.containers import _get_containers_data

"""Regression tests for container data task cleanup."""





@pytest.mark.asyncio
async def test_get_containers_data_cancels_docker_task_when_database_fails() -> None:
    docker_started = asyncio.Event()
    docker_cleaned_up = asyncio.Event()

    async def ps_all():
        docker_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            docker_cleaned_up.set()

    async def execute(_statement):
        await docker_started.wait()
        raise RuntimeError("database failed")

    docker_mgr = SimpleNamespace(ps_all=ps_all)
    db = SimpleNamespace(execute=execute)

    with pytest.raises(RuntimeError, match="database failed"):
        await _get_containers_data(db, docker_mgr)

    assert docker_cleaned_up.is_set()


@pytest.mark.asyncio
async def test_get_containers_data_cancels_database_task_when_docker_fails() -> None:
    database_started = asyncio.Event()
    database_cleaned_up = asyncio.Event()

    async def execute(_statement):
        database_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            database_cleaned_up.set()

    async def ps_all():
        await database_started.wait()
        raise RuntimeError("docker failed")

    docker_mgr = SimpleNamespace(ps_all=ps_all)
    db = SimpleNamespace(execute=execute)

    with pytest.raises(RuntimeError, match="docker failed"):
        await _get_containers_data(db, docker_mgr)

    assert database_cleaned_up.is_set()


@pytest.fixture
async def async_client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)

    engine = create_async_engine(s.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("pit_panel.db.session._engine", engine)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", sessionmaker)

    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client





@pytest.mark.asyncio
async def test_get_containers_data():
    class MockDB:
        async def execute(self, stmt):
            class ScalarResult:
                def scalars(self):
                    return self
                def all(self):
                    return [SimpleNamespace(id=1, subdomain="test1", app_type="wordpress")]
            return ScalarResult()

    class MockDockerMgr:
        async def ps_all(self):
            return [
                {"Names": "test-c", "Labels": "com.docker.compose.project=test1"},
                {"Name": "orphan-c", "Labels": ""}
            ]

    subdomains, containers_data, orphan_containers = await _get_containers_data(MockDB(), MockDockerMgr())
    assert len(subdomains) == 1
    assert 1 in containers_data
    assert len(containers_data[1]) == 1
    assert len(orphan_containers) == 1

@pytest.mark.asyncio
async def test_containers_list_no_user(async_client: AsyncClient):
    resp = await async_client.get("/containers", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"

    resp2 = await async_client.get("/containers", headers={"hx-request": "true"}, follow_redirects=False)
    assert resp2.status_code == 200
    assert resp2.headers["HX-Redirect"] == "/login"

@pytest.mark.asyncio
async def test_containers_list_authenticated(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    async def mock_get_containers_data(db, docker_mgr):
        return {"test1": SimpleNamespace(id=1, subdomain="test1")}, {1: [{"Name": "test-c"}]}, [{"Name": "orphan-c"}]
    monkeypatch.setattr("pit_panel.web.routes.containers._get_containers_data", mock_get_containers_data)

    resp = await async_client.get("/containers")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_container_logs_no_user(async_client: AsyncClient):
    resp = await async_client.get("/containers/1/logs", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"

    resp2 = await async_client.get("/containers/1/logs", headers={"hx-request": "true"}, follow_redirects=False)
    assert resp2.status_code == 200
    assert resp2.headers["HX-Redirect"] == "/login"

@pytest.mark.asyncio
async def test_container_logs_authenticated(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    import pit_panel.db.session
    sessionmaker = pit_panel.db.session._sessionmaker
    if sessionmaker is not None:
        async with sessionmaker() as db:
            sd1 = Subdomain(id=1, subdomain="test1", base_domain="example.com", owner_user_id=1)
            db.add(sd1)
            await db.commit()

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def compose_logs(self, subdomain, tail=200):
            return "log1\nlog2"
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/1/logs")
    assert resp.status_code == 200
    assert "log1" in resp.text

@pytest.mark.asyncio
async def test_container_logs_error(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    import pit_panel.db.session
    sessionmaker = pit_panel.db.session._sessionmaker
    if sessionmaker is not None:
        async with sessionmaker() as db:
            sd1 = Subdomain(id=1, subdomain="test1", base_domain="example.com", owner_user_id=1)
            db.add(sd1)
            await db.commit()

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def compose_logs(self, subdomain, tail=200):
            raise Exception("test error")
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/1/logs")
    assert resp.status_code == 200
    assert "Error fetching logs" in resp.text

@pytest.mark.asyncio
async def test_container_logs_not_found(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    resp = await async_client.get("/containers/999/logs", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/containers"

@pytest.mark.asyncio
async def test_container_restart_no_user(async_client: AsyncClient):
    resp = await async_client.post("/containers/1/restart", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"

    resp2 = await async_client.post("/containers/1/restart", headers={"hx-request": "true"}, follow_redirects=False)
    assert resp2.status_code == 200
    assert resp2.headers["HX-Redirect"] == "/login"

@pytest.mark.asyncio
async def test_container_restart_authenticated(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    import pit_panel.db.session
    sessionmaker = pit_panel.db.session._sessionmaker
    if sessionmaker is not None:
        async with sessionmaker() as db:
            sd1 = Subdomain(id=1, subdomain="test1", base_domain="example.com", owner_user_id=1)
            db.add(sd1)
            await db.commit()

    called = False
    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def run_compose_command(self, subdomain, cmd):
            nonlocal called
            called = True
            assert cmd == ["restart"]
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.post("/containers/1/restart", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/containers"
    assert called

@pytest.mark.asyncio
async def test_container_restart_not_found(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    resp = await async_client.post("/containers/999/restart", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/containers"


@pytest.mark.asyncio
async def test_container_stop_start_invalid(async_client: AsyncClient):
    resp = await async_client.post("/containers/container/invalid id/stop")
    assert resp.status_code == 400
    resp2 = await async_client.post("/containers/container/invalid id/start")
    assert resp2.status_code == 400

@pytest.mark.asyncio
async def test_container_stop_start_no_user(async_client: AsyncClient):
    resp = await async_client.post("/containers/container/valid-id/stop", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"

    resp2 = await async_client.post("/containers/container/valid-id/start", follow_redirects=False)
    assert resp2.status_code == 302
    assert resp2.headers["Location"] == "/login"

@pytest.mark.asyncio
async def test_container_stop_start_authenticated(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    stop_called = False
    start_called = False
    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def container_stop(self, cid):
            nonlocal stop_called
            stop_called = True
        async def container_start(self, cid):
            nonlocal start_called
            start_called = True
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.post("/containers/container/valid-id/stop", follow_redirects=False)
    assert resp.status_code == 302
    assert stop_called

    resp = await async_client.post("/containers/container/valid-id/start", follow_redirects=False)
    assert resp.status_code == 302
    assert start_called

@pytest.mark.asyncio
async def test_container_logs_live(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def container_logs_live(self, cid, tail=200):
            return "live logs"
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/container/valid-id/logs")
    assert resp.status_code == 200
    assert "live logs" in resp.text

@pytest.mark.asyncio
async def test_container_logs_live_error(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def container_logs_live(self, cid, tail=200):
            raise Exception("error live logs")
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/container/valid-id/logs")
    assert resp.status_code == 200
    assert "Error fetching logs" in resp.text

@pytest.mark.asyncio
async def test_container_logs_live_no_user_invalid(async_client: AsyncClient, monkeypatch: Any):
    resp2 = await async_client.get("/containers/container/invalid id/logs")
    assert resp2.status_code == 400

    resp3 = await async_client.get("/containers/container/valid-id/logs", follow_redirects=False)
    assert resp3.status_code == 302


@pytest.mark.asyncio
async def test_container_stats(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def container_stats(self, cid):
            return {"CPUPerc": "50.00%"}
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/container/valid-id/stats")
    assert resp.status_code == 200
    assert "50.00%" in resp.text

@pytest.mark.asyncio
async def test_container_stats_error(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def container_stats(self, cid):
            raise Exception("error stats")
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/container/valid-id/stats")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_container_stats_no_user_invalid(async_client: AsyncClient, monkeypatch: Any):
    resp2 = await async_client.get("/containers/container/invalid id/stats")
    assert resp2.status_code == 400

    resp3 = await async_client.get("/containers/container/valid-id/stats", follow_redirects=False)
    assert resp3.status_code == 302


@pytest.mark.asyncio
async def test_container_restart_no_sd(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockResult:
        def scalar_one_or_none(self):
            return None

    async def mock_execute(*args, **kwargs):
        return MockResult()
    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    resp = await async_client.post("/containers/999/restart", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/containers"

@pytest.mark.asyncio
async def test_container_logs_no_sd(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockResult:
        def scalar_one_or_none(self):
            return None

    async def mock_execute(*args, **kwargs):
        return MockResult()
    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    resp = await async_client.get("/containers/999/logs", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/containers"







@pytest.mark.asyncio
async def test_containers_fragment_authenticated(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    async def mock_get_containers_data(db, docker_mgr):
        return {"test1": SimpleNamespace(id=1, subdomain="test1")}, {1: [{"Name": "test-c"}]}, [{"Name": "orphan-c"}]
    monkeypatch.setattr("pit_panel.web.routes.containers._get_containers_data", mock_get_containers_data)

    resp = await async_client.get("/containers/fragment")
    assert resp.status_code == 200
    assert "test-c" in resp.text






@pytest.mark.asyncio
async def test_containers_fragment_redirects_no_user(async_client: AsyncClient):
    resp = await async_client.get("/containers/fragment")
    assert resp.status_code == 200
    assert resp.headers["HX-Redirect"] == "/login"







@pytest.mark.asyncio
async def test_container_logs_authenticated_db_mock(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockRow:
        def __init__(self, id, subdomain):
            self.id = id
            self.subdomain = subdomain

    class MockResult:
        def scalar_one_or_none(self):
            return MockRow(1, "test1")

    async def mock_execute(*args, **kwargs):
        return MockResult()

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def compose_logs(self, subdomain, tail=200):
            return "log1\nlog2"
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/1/logs")
    assert resp.status_code == 200
    assert "log1" in resp.text

@pytest.mark.asyncio
async def test_container_restart_authenticated_db_mock(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockRow:
        def __init__(self, id, subdomain):
            self.id = id
            self.subdomain = subdomain

    class MockResult:
        def scalar_one_or_none(self):
            return MockRow(1, "test1")

    async def mock_execute(*args, **kwargs):
        return MockResult()

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    called = False
    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def run_compose_command(self, subdomain, cmd):
            nonlocal called
            called = True
            assert cmd == ["restart"]
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.post("/containers/1/restart", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/containers"
    assert called


@pytest.mark.asyncio
async def test_container_logs_db_mock_not_found(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockResult:
        def scalar_one_or_none(self):
            return None

    async def mock_execute(*args, **kwargs):
        return MockResult()

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    resp = await async_client.get("/containers/999/logs", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/containers"

@pytest.mark.asyncio
async def test_container_logs_db_mock_error(async_client: AsyncClient, monkeypatch: Any):
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user
    monkeypatch.setattr("pit_panel.web.routes.containers.get_user", mock_get_user)

    class MockRow:
        def __init__(self, id, subdomain):
            self.id = id
            self.subdomain = subdomain

    class MockResult:
        def scalar_one_or_none(self):
            return MockRow(1, "test1")

    async def mock_execute(*args, **kwargs):
        return MockResult()

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    class MockDockerMgr:
        def __init__(self, *args, **kwargs):
            pass
        async def compose_logs(self, subdomain, tail=200):
            raise Exception("error fetching logs db mock")
    monkeypatch.setattr("pit_panel.web.routes.containers.DockerManager", MockDockerMgr)

    resp = await async_client.get("/containers/1/logs")
    assert resp.status_code == 200
    assert "Error fetching logs" in resp.text

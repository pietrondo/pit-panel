import pathlib
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Base, Subdomain, User
from pit_panel.web.app import create_app


@pytest.fixture
async def async_client(
    monkeypatch: Any, tmp_path: pathlib.Path
) -> AsyncGenerator[AsyncClient, None]:
    db_path = tmp_path / "test.db"
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)

    # Init real db for this test
    engine = create_async_engine(s.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr("pit_panel.db.session._engine", engine)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", sessionmaker)

    app = create_app(s)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client

@pytest.mark.asyncio
async def test_dashboard_redirects_to_login(async_client: AsyncClient) -> None:
    resp = await async_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"

@pytest.mark.asyncio
async def test_dashboard_authenticated(async_client: AsyncClient, monkeypatch: Any) -> None:
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user

    monkeypatch.setattr("pit_panel.web.routes.dashboard.get_user", mock_get_user)

    resp = await async_client.get("/")
    assert resp.status_code == 200
    assert "admin" in resp.text

@pytest.mark.asyncio
async def test_dashboard_authenticated_with_data(
    async_client: AsyncClient, monkeypatch: Any
) -> None:
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user

    monkeypatch.setattr("pit_panel.web.routes.dashboard.get_user", mock_get_user)

    import pit_panel.db.session
    sessionmaker = pit_panel.db.session._sessionmaker

    if sessionmaker is not None:
        async with sessionmaker() as db:
            sd1 = Subdomain(subdomain="test1", base_domain="example.com", owner_user_id=1)
            sd2 = Subdomain(
                subdomain="test2", base_domain="example.com", owner_user_id=1, app_type="wordpress"
            )
            db.add_all([sd1, sd2])
            await db.commit()

    resp = await async_client.get("/")
    assert resp.status_code == 200
    assert "admin" in resp.text

@pytest.mark.asyncio
async def test_dashboard_no_user(async_client: AsyncClient) -> None:
    resp = await async_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"

@pytest.mark.asyncio
async def test_dashboard_with_db_mock(async_client: AsyncClient, monkeypatch: Any) -> None:
    mock_user = User(id=1, username="admin")
    async def mock_get_user(request: Any, db: Any) -> User:
        return mock_user

    monkeypatch.setattr("pit_panel.web.routes.dashboard.get_user", mock_get_user)

    class MockRow:
        total = 5
        running = 2

    class MockResult:
        def first(self) -> MockRow:
            return MockRow()
        def scalars(self) -> 'MockResult':
            return self
        def all(self) -> Sequence[Any]:
            return []

    # Mock execute
    async def mock_execute(*args: Any, **kwargs: Any) -> MockResult:
        return MockResult()

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    resp = await async_client.get("/")
    assert resp.status_code == 200
    assert "admin" in resp.text

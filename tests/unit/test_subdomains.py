import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Base, User
from pit_panel.web.app import create_app


@pytest.fixture
def client(monkeypatch):
    # In-memory SQLite for testing
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url="sqlite+aiosqlite://",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)

    # Create engine and tables
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=None)

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # We must run this async function to initialize the DB.
    # A synchronous fixture using anyio or asyncio run will do.
    import asyncio

    asyncio.run(create_tables())

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("pit_panel.db.session._engine", engine)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", sessionmaker)

    # Mock get_user to return a dummy user
    async def override_get_user(req, db):
        return User(id=1, username="testadmin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.subdomains.get_user", override_get_user)

    # Mock _log_audit and caddy stuff to avoid DB calls inside audit log
    async def mock_log(*args, **kwargs):
        pass

    monkeypatch.setattr("pit_panel.web.routes.subdomains._log_audit", mock_log)

    app = create_app(s)
    return TestClient(app)


def test_subdomain_add_invalid(client):
    invalid_subdomains = ["../test", "test/123", "test..", "-test", "test-", r"test\123"]

    for sub in invalid_subdomains:
        resp = client.post("/subdomains/add", data={"subdomain": sub}, follow_redirects=False)
        assert resp.status_code == 200, f"Expected 200 (error rendering template) for {sub}"
        assert "Invalid subdomain name" in resp.text, f"Expected validation error for {sub}"


def test_subdomain_add_valid(client):
    valid_subdomains = ["test", "test-app", "t123"]

    for sub in valid_subdomains:
        resp = client.post("/subdomains/add", data={"subdomain": sub}, follow_redirects=False)
        assert resp.status_code == 302, f"Expected 302 redirect for {sub}"
        assert resp.headers["location"] == "/subdomains", (
            f"Expected redirect to /subdomains for {sub}"
        )

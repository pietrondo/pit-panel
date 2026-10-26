"""The schema must follow the models on an existing database.

A deploy that adds a column used to leave the table untouched (create_all only
creates missing tables), so the panel answered 500 on every page that selected a
subdomain while /health stayed green.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from pit_panel.config import Settings
from pit_panel.db.models import Base
from pit_panel.db.schema_sync import missing_columns, sync_schema
from pit_panel.web.app import create_app


async def _drop_host_port(engine) -> None:
    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP INDEX ix_subdomains_host_port")
        await conn.exec_driver_sql("ALTER TABLE subdomains DROP COLUMN host_port")


@pytest.mark.asyncio
async def test_sync_adds_the_missing_column_and_its_index(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _drop_host_port(engine)

    assert "subdomains.host_port" in await missing_columns(engine)

    assert await sync_schema(engine) == ["subdomains.host_port"]
    assert await missing_columns(engine) == []

    async with engine.begin() as conn:
        indexes = await conn.exec_driver_sql("PRAGMA index_list('subdomains')")
        names = {row[1] for row in indexes.fetchall()}
    assert "ix_subdomains_host_port" in names

    # A second pass changes nothing.
    assert await sync_schema(engine) == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_is_red_when_the_schema_is_stale(tmp_path, monkeypatch):
    import pit_panel.db.session as db_session

    settings = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'stale.db'}",
    )
    # /health reads the process-wide engine: point it at this database.
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_sessionmaker", None)

    engine = create_async_engine(settings.get_database_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _drop_host_port(engine)
    await engine.dispose()

    app = create_app(settings)
    # ASGITransport does not run the lifespan, so the startup reconciliation
    # does not mask the stale schema.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert "subdomains.host_port" in response.json()["missing"]

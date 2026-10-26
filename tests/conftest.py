import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.db.models import Base

# Set default test paths before any config is loaded
os.environ["PITPANEL_DATA_DIR"] = "/tmp/pit-panel-data"
os.environ["PITPANEL_APPS_DIR"] = "/tmp/pit-panel-apps"


@pytest.fixture(autouse=True)
def _reset_docker_cache():
    from pit_panel.core.docker_ops import DockerManager

    DockerManager._ps_all_cache = None
    yield
    DockerManager._ps_all_cache = None


def create_schema_sync(url: str) -> None:
    """Create the tables without running the app lifespan (no background loops)."""
    import asyncio

    async def _run() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_run())


@pytest.fixture
def schema_creator():
    """Fixture form of create_schema_sync, so tests need no cross-module import."""
    return create_schema_sync


@pytest.fixture
def settings():
    from pit_panel.config import Settings

    return Settings(secret_key="test-secret-key-32chars-long!!", debug=True)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        yield db

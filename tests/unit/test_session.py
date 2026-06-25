import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import pit_panel.db.session as session_module
from pit_panel.config import Settings


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global variables to ensure clean state for each test."""
    session_module._engine = None
    session_module._sessionmaker = None
    yield
    session_module._engine = None
    session_module._sessionmaker = None


class TestSession:
    def test_get_engine(self):
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:", debug=True)
        engine = session_module.get_engine(settings)
        assert isinstance(engine, AsyncEngine)
        assert engine.url.render_as_string(hide_password=False) == "sqlite+aiosqlite:///:memory:"
        assert engine.echo is True

    def test_get_engine_singleton(self):
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        engine1 = session_module.get_engine(settings)
        engine2 = session_module.get_engine(settings)
        assert engine1 is engine2

    def test_get_sessionmaker(self):
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        sm = session_module.get_sessionmaker(settings)
        assert isinstance(sm, async_sessionmaker)

    def test_get_sessionmaker_singleton(self):
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        sm1 = session_module.get_sessionmaker(settings)
        sm2 = session_module.get_sessionmaker(settings)
        assert sm1 is sm2

    @pytest.mark.asyncio
    async def test_get_db(self):
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        session_module.get_sessionmaker(settings)

        async for session in session_module.get_db():
            assert isinstance(session, AsyncSession)
            break

    @pytest.mark.asyncio
    async def test_init_db(self):
        settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
        await session_module.init_db(settings)
        engine = session_module.get_engine(settings)

        def check_tables(conn):
            from sqlalchemy import inspect

            inspector = inspect(conn)
            return inspector.get_table_names()

        async with engine.connect() as conn:
            tables = await conn.run_sync(check_tables)
            assert "users" in tables
            assert "subdomains" in tables

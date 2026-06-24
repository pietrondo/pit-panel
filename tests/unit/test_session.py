from collections.abc import Generator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import pit_panel.db.session as session_mod
from pit_panel.config import Settings


@pytest.fixture(autouse=True)
def reset_globals() -> Generator[None, None, None]:
    """Reset the global state in pit_panel.db.session before each test."""
    original_engine = session_mod._engine
    original_sessionmaker = session_mod._sessionmaker
    session_mod._engine = None
    session_mod._sessionmaker = None
    yield
    session_mod._engine = original_engine
    session_mod._sessionmaker = original_sessionmaker


class TestSession:
    def test_get_engine(self, settings: Settings) -> None:
        engine1 = session_mod.get_engine(settings)
        assert isinstance(engine1, AsyncEngine)
        assert engine1.echo == settings.debug

        # Test singleton behavior
        engine2 = session_mod.get_engine(settings)
        assert engine1 is engine2

    def test_get_engine_no_settings(self) -> None:
        engine1 = session_mod.get_engine()
        assert isinstance(engine1, AsyncEngine)

        # Test singleton behavior
        engine2 = session_mod.get_engine()
        assert engine1 is engine2

    def test_get_sessionmaker(self, settings: Settings) -> None:
        maker1 = session_mod.get_sessionmaker(settings)
        assert isinstance(maker1, async_sessionmaker)

        # Test singleton behavior
        maker2 = session_mod.get_sessionmaker(settings)
        assert maker1 is maker2

    @pytest.mark.asyncio
    async def test_get_db(self) -> None:
        # We can just test that the generator yields an AsyncSession
        generator = session_mod.get_db()
        async for session in generator:
            assert isinstance(session, AsyncSession)
            break

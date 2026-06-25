from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import pit_panel.db.session
from pit_panel.config import Settings
from pit_panel.db.session import get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
def reset_globals() -> Generator[None, Any, None]:
    """Reset the global variables in the session module before and after each test."""
    pit_panel.db.session._engine = None
    pit_panel.db.session._sessionmaker = None
    yield
    pit_panel.db.session._engine = None
    pit_panel.db.session._sessionmaker = None


def test_get_engine(settings: Settings) -> None:
    engine1 = get_engine(settings)
    assert isinstance(engine1, AsyncEngine)
    # create_async_engine returns an engine with url, settings.get_database_url() might be sqlite+aiosqlite:///...
    assert str(engine1.url) == settings.get_database_url()

    # Should return the same instance (singleton pattern)
    engine2 = get_engine(settings)
    assert engine1 is engine2


def test_get_engine_no_settings() -> None:
    engine = get_engine()
    assert isinstance(engine, AsyncEngine)


def test_get_sessionmaker(settings: Settings) -> None:
    sm1 = get_sessionmaker(settings)
    assert isinstance(sm1, async_sessionmaker)

    # Should return the same instance (singleton pattern)
    sm2 = get_sessionmaker(settings)
    assert sm1 is sm2

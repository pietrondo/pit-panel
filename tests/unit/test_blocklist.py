import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.core import blocklist
from pit_panel.core.blocklist import (
    BLOCKLIST_SOURCES,
    daily_blocklist_import,
    fetch_blocklist,
)
from pit_panel.db.models import Base


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        yield db


@pytest.fixture(autouse=True)
def clear_cache():
    blocklist._BLOCKLIST_CACHE.clear()


@pytest.mark.asyncio
async def test_fetch_blocklist_success(monkeypatch):
    class MockResponse:
        status_code = 200
        text = "1.2.3.4\n5.6.7.8\n# comment\n9.10.11.12 some text\n"

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == ["1.2.3.4", "5.6.7.8", "9.10.11.12"]


@pytest.mark.asyncio
async def test_fetch_blocklist_cache(monkeypatch):
    # Pre-populate cache
    blocklist._BLOCKLIST_CACHE["http://example.com/list"] = (["1.1.1.1"], time.time())

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == ["1.1.1.1"]


@pytest.mark.asyncio
async def test_fetch_blocklist_cache_expired(monkeypatch):
    # Pre-populate cache with expired timestamp
    blocklist._BLOCKLIST_CACHE["http://example.com/list"] = (["1.1.1.1"], time.time() - 4000)

    class MockResponse:
        status_code = 200
        text = "2.2.2.2\n"

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == ["2.2.2.2"]


@pytest.mark.asyncio
async def test_fetch_blocklist_http_error(monkeypatch):
    class MockResponse:
        status_code = 404

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == []


@pytest.mark.asyncio
async def test_fetch_blocklist_exception(monkeypatch):
    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url):
            raise ValueError("Network error")

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == []


@pytest.mark.asyncio
async def test_daily_blocklist_import(monkeypatch):
    # We want to run one iteration and then stop the infinite loop.
    sleep_calls = 0

    async def mock_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    # Mock settings
    class MockSettings:
        auto_blocklist = True

    monkeypatch.setattr("pit_panel.core.blocklist.get_settings", lambda: MockSettings())

    # Mock session
    mock_session = AsyncMock()
    mock_sessionmaker = Mock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    monkeypatch.setattr("pit_panel.core.blocklist.get_sessionmaker", lambda: mock_sessionmaker)

    # Mock fetch and ban
    mock_fetch = AsyncMock(return_value=["1.1.1.1"])
    monkeypatch.setattr("pit_panel.core.blocklist.fetch_blocklist", mock_fetch)

    mock_ban = AsyncMock()
    monkeypatch.setattr("pit_panel.core.blocklist.ban_ips_bulk", mock_ban)

    # Run
    with contextlib.suppress(asyncio.CancelledError):
        await daily_blocklist_import()

    assert sleep_calls == 2
    assert mock_fetch.call_count == len(BLOCKLIST_SOURCES)
    assert mock_ban.call_count == len(BLOCKLIST_SOURCES)


@pytest.mark.asyncio
async def test_daily_blocklist_import_disabled(monkeypatch):
    # Run one iteration, auto_blocklist = False
    sleep_calls = 0

    async def mock_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    class MockSettings:
        auto_blocklist = False

    monkeypatch.setattr("pit_panel.core.blocklist.get_settings", lambda: MockSettings())

    mock_fetch = AsyncMock()
    monkeypatch.setattr("pit_panel.core.blocklist.fetch_blocklist", mock_fetch)

    with contextlib.suppress(asyncio.CancelledError):
        await daily_blocklist_import()

    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_daily_blocklist_import_exception(monkeypatch):
    sleep_calls = 0

    async def mock_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    class MockSettings:
        auto_blocklist = True

    monkeypatch.setattr("pit_panel.core.blocklist.get_settings", lambda: MockSettings())

    mock_session = AsyncMock()
    mock_sessionmaker = Mock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    monkeypatch.setattr("pit_panel.core.blocklist.get_sessionmaker", lambda: mock_sessionmaker)

    # Mock fetch to raise exception
    mock_fetch = AsyncMock(side_effect=Exception("Test error"))
    monkeypatch.setattr("pit_panel.core.blocklist.fetch_blocklist", mock_fetch)

    with contextlib.suppress(asyncio.CancelledError):
        await daily_blocklist_import()

    assert sleep_calls == 2

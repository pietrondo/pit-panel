import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pit_panel.core.blocklist import (
    _BLOCKLIST_CACHE,
    CACHE_TTL,
    daily_blocklist_import,
    fetch_blocklist,
)


class MockResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

@pytest.fixture(autouse=True)
def clear_cache():
    _BLOCKLIST_CACHE.clear()
    yield
    _BLOCKLIST_CACHE.clear()

@pytest.mark.asyncio
async def test_fetch_blocklist_success(monkeypatch):
    mock_resp = MockResponse(200, "192.168.1.1\n192.168.1.2\n# Comment\n\n192.168.1.3 extra")

    class LocalMockClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            return mock_resp

    monkeypatch.setattr("httpx.AsyncClient", LocalMockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == ["192.168.1.1", "192.168.1.2", "192.168.1.3"]
    assert "http://example.com/list" in _BLOCKLIST_CACHE

@pytest.mark.asyncio
async def test_fetch_blocklist_cache(monkeypatch):
    # Set cache directly
    _BLOCKLIST_CACHE["http://example.com/list"] = (["1.1.1.1"], time.time())

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            raise Exception("Should not be called")

    monkeypatch.setattr("httpx.AsyncClient", FailingClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == ["1.1.1.1"]

@pytest.mark.asyncio
async def test_fetch_blocklist_cache_expired(monkeypatch):
    _BLOCKLIST_CACHE["http://example.com/list"] = (["1.1.1.1"], time.time() - CACHE_TTL - 1)

    mock_resp = MockResponse(200, "2.2.2.2")
    class LocalMockClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            return mock_resp

    monkeypatch.setattr("httpx.AsyncClient", LocalMockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == ["2.2.2.2"]

@pytest.mark.asyncio
async def test_fetch_blocklist_not_200(monkeypatch):
    mock_resp = MockResponse(404, "")
    class LocalMockClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            return mock_resp

    monkeypatch.setattr("httpx.AsyncClient", LocalMockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == []

@pytest.mark.asyncio
async def test_fetch_blocklist_exception(monkeypatch):
    class LocalMockClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            raise Exception("Network error")

    monkeypatch.setattr("httpx.AsyncClient", LocalMockClient)

    ips = await fetch_blocklist("http://example.com/list")
    assert ips == []


@pytest.mark.asyncio
async def test_daily_blocklist_import(monkeypatch):
    # Mock asyncio.sleep to not block on the first call but raise on the second
    sleep_calls = 0
    async def mock_sleep(seconds):
        nonlocal sleep_calls
        if sleep_calls > 0:
            raise asyncio.CancelledError()
        sleep_calls += 1

    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    mock_settings = MagicMock()
    mock_settings.auto_blocklist = True
    monkeypatch.setattr("pit_panel.core.blocklist.get_settings", lambda: mock_settings)

    class MockDbSession:
        async def __aenter__(self):
            return "mock_db"
        async def __aexit__(self, *args):
            pass

    class MockSessionMaker:
        def __call__(self):
            return MockDbSession()
    monkeypatch.setattr("pit_panel.core.blocklist.get_sessionmaker", MockSessionMaker)

    mock_fetch = AsyncMock(return_value=["3.3.3.3"])
    monkeypatch.setattr("pit_panel.core.blocklist.fetch_blocklist", mock_fetch)

    mock_ban = AsyncMock()
    monkeypatch.setattr("pit_panel.core.blocklist.ban_ips_bulk", mock_ban)

    with pytest.raises(asyncio.CancelledError):
        await daily_blocklist_import()

    assert mock_fetch.call_count > 0
    assert mock_ban.call_count > 0

@pytest.mark.asyncio
async def test_daily_blocklist_import_disabled(monkeypatch):
    sleep_calls = 0
    async def mock_sleep(seconds):
        nonlocal sleep_calls
        if sleep_calls > 0:
            raise asyncio.CancelledError()
        sleep_calls += 1

    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    mock_settings = MagicMock()
    mock_settings.auto_blocklist = False
    monkeypatch.setattr("pit_panel.core.blocklist.get_settings", lambda: mock_settings)

    mock_fetch = AsyncMock()
    monkeypatch.setattr("pit_panel.core.blocklist.fetch_blocklist", mock_fetch)

    with pytest.raises(asyncio.CancelledError):
        await daily_blocklist_import()

    assert mock_fetch.call_count == 0


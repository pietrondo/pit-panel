"""A Dynu root that is not delegated cannot serve any subdomain."""

import pytest

from pit_panel.core import dns_check


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, *args, **kwargs):
        if self._error:
            raise self._error
        return _Response(self._payload)


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    monkeypatch.setattr(dns_check, "_CACHE", {})


@pytest.mark.asyncio
async def test_delegated_root_has_no_warning(monkeypatch):
    payload = {
        "Answer": [
            {"type": 2, "data": "ns1.dynu.com."},
            {"type": 2, "data": "ns2.dynu.com."},
        ]
    }
    monkeypatch.setattr(dns_check.httpx, "AsyncClient", lambda **_: _Client(payload))

    assert await dns_check.name_servers("1cooldns.org") == ["ns1.dynu.com.", "ns2.dynu.com."]
    assert await dns_check.root_problem("1cooldns.org") is None


@pytest.mark.asyncio
async def test_undelegated_root_is_reported(monkeypatch):
    # NXDOMAIN: no Answer at all, which is the state of a domain nobody delegated.
    monkeypatch.setattr(dns_check.httpx, "AsyncClient", lambda **_: _Client({"Status": 3}))

    warning = await dns_check.root_problem("1cooldns.org")

    assert warning is not None
    assert "no NS records" in warning
    assert "1cooldns.org" in warning


@pytest.mark.asyncio
async def test_lookup_failure_does_not_warn(monkeypatch):
    monkeypatch.setattr(
        dns_check.httpx, "AsyncClient", lambda **_: _Client(error=OSError("offline"))
    )

    assert await dns_check.name_servers("1cooldns.org") is None
    assert await dns_check.root_problem("1cooldns.org") is None

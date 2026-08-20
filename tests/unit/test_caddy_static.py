"""Tests for CaddyManager static subdomain methods (file_server handler)."""

from unittest.mock import AsyncMock, patch

import pytest

from pit_panel.core.caddy import CaddyManager


def _make_mock_client():
    client = AsyncMock()
    resp_ok = AsyncMock()
    resp_ok.status_code = 200
    resp_ok.text = ""
    resp_ok.json.return_value = {}
    resp_ok.raise_for_status = lambda: None
    resp_404 = AsyncMock()
    resp_404.status_code = 404
    resp_post_ok = AsyncMock()
    resp_post_ok.status_code = 200
    resp_post_ok.text = ""
    resp_post_ok.json.return_value = {}
    resp_post_ok.raise_for_status = lambda: None
    client.patch.return_value = resp_ok
    client.post.return_value = resp_post_ok
    client.delete.return_value = resp_ok
    return client


@pytest.mark.asyncio
async def test_add_static_subdomain_sends_correct_route():
    client = _make_mock_client()
    mgr = CaddyManager("http://127.0.0.1:2019")
    with patch("pit_panel.core.caddy.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__.return_value = client
        mock_ac.return_value.__aexit__.return_value = False
        await mgr.add_static_subdomain("mysite", "example.com", "/var/www/mysite")

    assert client.patch.await_count == 1
    args, kwargs = client.patch.call_args
    assert args[0] == "http://127.0.0.1:2019/id/static-mysite.example.com"
    route = kwargs["json"]
    assert route["@id"] == "static-mysite.example.com"
    assert route["match"] == [{"host": ["mysite.example.com"]}]
    handlers = route["handle"]
    assert handlers[0]["handler"] == "filesystem"
    assert handlers[0]["root"] == "/var/www/mysite"
    assert handlers[0]["index"] == "index.html"
    assert handlers[1] == {"handler": "file_server", "hide": [".*"]}


@pytest.mark.asyncio
async def test_add_static_subdomain_falls_back_to_post_on_404():
    client = _make_mock_client()
    client.patch.return_value.status_code = 404
    mgr = CaddyManager("http://127.0.0.1:2019")
    with patch("pit_panel.core.caddy.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__.return_value = client
        mock_ac.return_value.__aexit__.return_value = False
        await mgr.add_static_subdomain("a", "b.com", "/x")

    assert client.patch.await_count == 1
    assert client.post.await_count == 1
    args, _ = client.post.call_args
    assert args[0] == "http://127.0.0.1:2019/config/apps/http/servers/srv0/routes/"


@pytest.mark.asyncio
async def test_remove_static_subdomain_uses_correct_route_id():
    client = _make_mock_client()
    mgr = CaddyManager("http://127.0.0.1:2019")
    with patch("pit_panel.core.caddy.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__.return_value = client
        mock_ac.return_value.__aexit__.return_value = False
        await mgr.remove_static_subdomain("mysite", "example.com")

    args, _ = client.delete.call_args
    assert args[0] == "http://127.0.0.1:2019/id/static-mysite.example.com"

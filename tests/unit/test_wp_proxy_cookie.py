"""The panel session cookie must never reach a tenant container."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import Request

from pit_panel.core.wp_proxy import proxy_request


@pytest.mark.asyncio
async def test_proxy_strips_panel_cookie_and_authorization():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/apps/3/wp/x",
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"cookie", b"pitpanel_session=secret"),
            (b"authorization", b"Bearer secret"),
            (b"x-custom-header", b"custom-value"),
        ],
        "path_params": {"path": "x"},
    }
    request = Request(scope)

    async def mock_receive():
        return {"type": "http.request", "body": b""}

    request._receive = mock_receive

    mock_resp = AsyncMock()
    mock_resp.content = b"ok"
    mock_resp.headers = httpx.Headers({"content-type": "text/plain"})
    mock_resp.status_code = 200

    mock_client_instance = AsyncMock()
    mock_client_instance.request = AsyncMock(return_value=mock_resp)
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client_instance

    with patch("pit_panel.core.wp_proxy.httpx.AsyncClient", return_value=mock_client):
        await proxy_request(request, 8081, 3)

    headers = mock_client_instance.request.call_args.kwargs["headers"]
    assert "cookie" not in headers
    assert "authorization" not in headers
    assert headers["x-custom-header"] == "custom-value"

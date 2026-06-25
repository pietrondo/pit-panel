import datetime as dt

import httpx
import pytest
from pytest_httpx import HTTPXMock

from pit_panel.core.caddy import CaddyManager


@pytest.fixture
def caddy() -> CaddyManager:
    return CaddyManager(admin_url="http://mock-caddy:2019")


@pytest.mark.asyncio
async def test_add_subdomain(caddy: CaddyManager, httpx_mock: HTTPXMock):
    fqdn = "test.example.com"
    httpx_mock.add_response(
        method="PATCH",
        url=f"http://mock-caddy:2019/id/{fqdn}",
        json={"status": "ok"},
    )

    result = await caddy.add_subdomain("test", "example.com", 8080)

    assert result == {"status": "ok"}
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "PATCH"
    import json

    content = json.loads(request.read())
    assert content == {
        "@id": fqdn,
        "match": [{"host": [fqdn]}],
        "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "127.0.0.1:8080"}]}],
    }


@pytest.mark.asyncio
async def test_remove_subdomain(caddy: CaddyManager, httpx_mock: HTTPXMock):
    fqdn = "test.example.com"
    httpx_mock.add_response(
        method="DELETE",
        url=f"http://mock-caddy:2019/id/{fqdn}",
        json={"status": "ok"},
    )

    result = await caddy.remove_subdomain("test", "example.com")

    assert result == {"status": "ok"}
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "DELETE"


@pytest.mark.asyncio
async def test_list_subdomains(caddy: CaddyManager, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url="http://mock-caddy:2019/config/apps/http/servers/srv0/routes",
        json=[{"@id": "test1.example.com"}, {"@id": "test2.example.com"}, {"other": "data"}],
    )

    result = await caddy.list_subdomains()

    assert result == ["test1.example.com", "test2.example.com"]
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "GET"


@pytest.mark.asyncio
async def test_list_subdomains_empty(caddy: CaddyManager, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url="http://mock-caddy:2019/config/apps/http/servers/srv0/routes",
        text="null", # Caddy API returns "null" when there are no routes
    )

    result = await caddy.list_subdomains()

    assert result == []


@pytest.mark.asyncio
async def test_setup_panel_route(caddy: CaddyManager, httpx_mock: HTTPXMock):
    fqdn = "panel.example.com"
    httpx_mock.add_response(
        method="PATCH",
        url=f"http://mock-caddy:2019/id/panel-{fqdn}",
        json={"status": "ok"},
    )

    result = await caddy.setup_panel_route("panel", "example.com", 8080)

    assert result == {"status": "ok"}
    request = httpx_mock.get_request()
    assert request is not None
    import json

    content = json.loads(request.read())
    assert content == {
        "@id": f"panel-{fqdn}",
        "match": [{"host": [fqdn]}],
        "handle": [
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": "127.0.0.1:8080"}],
            }
        ],
    }


@pytest.mark.asyncio
async def test_get_certificates(caddy: CaddyManager, httpx_mock: HTTPXMock):
    now = dt.datetime.now(dt.UTC)
    not_after = (now + dt.timedelta(days=30)).isoformat().replace("+00:00", "Z")

    httpx_mock.add_response(
        method="GET",
        url="http://mock-caddy:2019/pki/ca/local/certificates",
        json=[
            {
                "serial_number": "12345678901234567890",
                "sans": ["example.com", "www.example.com"],
                "not_before": "2023-01-01T00:00:00Z",
                "not_after": not_after,
                "issuer": {"common_name": "Test CA"},
            },
            {
                "serial_number": "short",
            },
        ],
    )

    result = await caddy.get_certificates()

    assert len(result) == 2
    assert result[0]["serial"] == "1234567890123456"
    assert result[0]["domains"] == "example.com, www.example.com"
    assert result[0]["not_before"] == "2023-01-01T00:00:00Z"
    assert result[0]["not_after"] == not_after
    assert (
        result[0]["expires_in_days"] == 29 or result[0]["expires_in_days"] == 30
    )  # Account for time differences
    assert result[0]["issuer"] == "Test CA"

    assert result[1]["serial"] == "short"
    assert result[1]["domains"] == ""
    assert result[1]["expires_in_days"] is None


@pytest.mark.asyncio
async def test_get_certificates_error(caddy: CaddyManager, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ReadTimeout("Timeout"), url="http://mock-caddy:2019/pki/ca/local/certificates"
    )

    result = await caddy.get_certificates()

    assert result == []


@pytest.mark.asyncio
async def test_renew_certificate_success(caddy: CaddyManager, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="http://mock-caddy:2019/pki/ca/local/certificates?renew=true",
        json={"status": "renewed"},
    )

    result = await caddy.renew_certificate("example.com")

    assert result == {"success": True, "domain": "example.com"}
    request = httpx_mock.get_request()
    import json

    content = json.loads(request.read())
    assert content == {"sans": ["example.com"]}


@pytest.mark.asyncio
async def test_renew_certificate_error(caddy: CaddyManager, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url="http://mock-caddy:2019/pki/ca/local/certificates?renew=true",
    )

    result = await caddy.renew_certificate("example.com")

    assert result["success"] is False
    assert result["domain"] == "example.com"
    assert "Connection refused" in result["error"]

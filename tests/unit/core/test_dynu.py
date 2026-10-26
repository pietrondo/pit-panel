import httpx
import pytest

from pit_panel.core.dynu import DynuClient, DynuError


def handler_for_records(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v2/dns":
        return httpx.Response(200, json=[{"id": 42, "name": "example.dynu.net"}])
    if request.method == "GET" and request.url.path.endswith("/record"):
        return httpx.Response(200, json=[])
    return httpx.Response(200, json={"id": 99, "hostname": "app.example.dynu.net"})


@pytest.mark.asyncio
async def test_add_record_resolves_domain_and_posts_v2_record():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler_for_records(request)

    result = await DynuClient("secret", transport=httpx.MockTransport(handler)).add_a_record(
        "example.dynu.net", "app", "203.0.113.10"
    )
    assert result["id"] == 99
    assert requests[0].headers["API-Key"] == "secret"
    assert requests[2].content == (
        b'{"nodeName":"app","recordType":"A","ipv4Address":"203.0.113.10","ttl":300,"state":true}'
    )


@pytest.mark.asyncio
async def test_delete_record_requires_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/dns":
            return httpx.Response(200, json=[{"id": 42, "name": "example.dynu.net"}])
        if request.method == "GET" and request.url.path.endswith("/record"):
            return httpx.Response(200, json=[{"id": 99, "nodeName": "app", "recordType": "A"}])
        return httpx.Response(204)

    await DynuClient("secret", transport=httpx.MockTransport(handler)).delete_a_record(
        "example.dynu.net", "app"
    )


@pytest.mark.asyncio
async def test_missing_domain_raises_without_mutating():
    with pytest.raises(DynuError, match="not found"):
        await DynuClient(
            "secret", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))
        ).add_a_record("missing.dynu.net", "app", "203.0.113.10")


@pytest.mark.asyncio
async def test_add_rejects_existing_a_or_cname_record():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/dns":
            return httpx.Response(200, json=[{"id": 1, "name": "root.dynu.net"}])
        return httpx.Response(200, json=[{"id": 7, "nodeName": "app", "recordType": "CNAME"}])

    with pytest.raises(DynuError, match="already exists"):
        await DynuClient("k", transport=httpx.MockTransport(handler)).add_a_record(
            "root.dynu.net", "app", "1.2.3.4"
        )


@pytest.mark.asyncio
async def test_list_domains_reads_every_root_in_the_account():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"id": 1, "name": "one.dynu.net"},
                {"id": 2, "name": "two.org."},
                {"id": 3},
            ],
        )

    roots = await DynuClient("k", transport=httpx.MockTransport(handler)).list_domains()

    assert roots == ["one.dynu.net", "two.org"]


@pytest.mark.asyncio
async def test_available_roots_returns_none_without_a_key():
    from types import SimpleNamespace

    from pit_panel.core.dynu import available_roots

    assert await available_roots(SimpleNamespace(dynu_api_key="")) is None

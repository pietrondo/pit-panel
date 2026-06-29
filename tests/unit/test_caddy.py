from unittest.mock import AsyncMock, patch

import pytest

from pit_panel.core.caddy import CaddyManager


class TestMainDomain:
    @pytest.mark.asyncio
    async def test_add_main_domain(self):
        mgr = CaddyManager("http://127.0.0.1:2019")
        mock_resp = AsyncMock()
        mock_resp.text = ""
        mock_resp.json.return_value = {}

        with patch.object(mgr, "_patch_or_create_route", AsyncMock(return_value={})) as mock_patch:
            await mgr.add_main_domain("example.com", port=8080)

            mock_patch.assert_called_once()
            route = mock_patch.call_args[0][0]
            assert route["@id"] == "main-example.com"
            assert route["match"] == [{"host": ["example.com"]}]
            assert route["handle"][0]["handler"] == "reverse_proxy"
            assert route["handle"][0]["upstreams"] == [{"dial": "127.0.0.1:8080"}]

    @pytest.mark.asyncio
    async def test_add_main_domain_default_port(self):
        mgr = CaddyManager("http://127.0.0.1:2019")

        with patch.object(mgr, "_patch_or_create_route", AsyncMock(return_value={})) as mock_patch:
            await mgr.add_main_domain("example.com")
            route = mock_patch.call_args[0][0]
            assert route["handle"][0]["upstreams"] == [{"dial": "127.0.0.1:80"}]

    @pytest.mark.asyncio
    async def test_remove_main_domain(self):
        mgr = CaddyManager("http://127.0.0.1:2019")

        with patch.object(mgr, "_delete_route", AsyncMock(return_value={})) as mock_delete:
            await mgr.remove_main_domain("example.com")
            mock_delete.assert_called_once_with("main-example.com")


@pytest.mark.asyncio
async def test_get_certificates_api_success():
    mgr = CaddyManager()
    with (
        patch.object(mgr, "_get_managed_domains", AsyncMock(return_value=["panel.example.com"])),
        patch.object(
            mgr,
            "_check_certs_via_openssl",
            return_value=[
                {"serial": "abc", "domains": "panel.example.com", "issuer": "Let's Encrypt"}
            ],
        ),
    ):
        certs = await mgr.get_certificates()
        assert len(certs) == 1
        assert certs[0]["domains"] == "panel.example.com"


@pytest.mark.asyncio
async def test_get_certificates_handles_api_error():
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get.side_effect = Exception("timeout")

    with patch("httpx.AsyncClient", return_value=mock_client):
        mgr = CaddyManager()
        certs = await mgr.get_certificates()
        assert certs == []

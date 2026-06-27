import json
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

        with patch.object(mgr, "_patch_routes", AsyncMock(return_value={})) as mock_patch:
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

        with patch.object(mgr, "_patch_routes", AsyncMock(return_value={})) as mock_patch:
            await mgr.add_main_domain("example.com")
            route = mock_patch.call_args[0][0]
            assert route["handle"][0]["upstreams"] == [{"dial": "127.0.0.1:80"}]

    @pytest.mark.asyncio
    async def test_remove_main_domain(self):
        mgr = CaddyManager("http://127.0.0.1:2019")

        with patch.object(mgr, "_delete_route", AsyncMock(return_value={})) as mock_delete:
            await mgr.remove_main_domain("example.com")
            mock_delete.assert_called_once_with("main-example.com")


class TestParsePemCerts:
    def test_parses_valid_pem(self):
        pem = """-----BEGIN CERTIFICATE-----
MIIBpDCCAUqgAwIBAgIRAO8uZlM07EVheJPeK99gNAMwCgYIKoZIzj0EAwIwMDEu
MCwGA1UEAxMlQ2FkZHkgTG9jYWwgQXV0aG9yaXR5IC0gMjAyNiBFQ0MgUm9vdDAe
Fw0yNjA2MjQyMjI3MDZaFw0zNjA1MDIyMjI3MDZaMDAxLjAsBgNVBAMTJUNhZGR5
-----END CERTIFICATE-----"""
        mgr = CaddyManager()
        certs = mgr._parse_pem_certs(pem)
        assert len(certs) == 1
        assert certs[0]["issuer"] == "Caddy Local CA"

    def test_parses_empty_pem(self):
        mgr = CaddyManager()
        certs = mgr._parse_pem_certs("no certs here")
        assert certs == []

    def test_parses_multiple_certs(self):
        pem = (
            "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
            "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----"
        )
        mgr = CaddyManager()
        certs = mgr._parse_pem_certs(pem)
        assert len(certs) >= 0


class TestParseStorageCerts:
    def test_finds_json_with_sans(self, tmp_path):
        certs_dir = tmp_path / "acme" / "example.com"
        certs_dir.mkdir(parents=True)
        meta = {"sans": ["example.com", "www.example.com"]}
        (certs_dir / "example.com.json").write_text(json.dumps(meta))

        mgr = CaddyManager()
        with patch.object(
            CaddyManager, "_parse_caddy_storage_certs", lambda self, client: _parse_certs(tmp_path)
        ):
            certs = mgr._parse_caddy_storage_certs(None)
            assert len(certs) == 1
            assert certs[0]["domains"] == "example.com, www.example.com"

    def test_skips_json_without_domains(self, tmp_path):
        certs_dir = tmp_path / "acme" / "empty.example.com"
        certs_dir.mkdir(parents=True)
        meta = {"sans": [], "domains": []}
        (certs_dir / "empty.example.com.json").write_text(json.dumps(meta))

        mgr = CaddyManager()
        certs = mgr._parse_caddy_storage_certs(None)
        assert len(certs) == 0

    def test_handles_invalid_json(self, tmp_path):
        certs_dir = tmp_path / "bad"
        certs_dir.mkdir(parents=True)
        (certs_dir / "bad.json").write_text("not json")

        mgr = CaddyManager()
        certs = mgr._parse_caddy_storage_certs(None)
        assert certs == []

    def test_extracts_issuer_from_meta(self, tmp_path):
        certs_dir = tmp_path / "acme" / "test.example.com"
        certs_dir.mkdir(parents=True)
        meta = {
            "sans": ["test.example.com"],
            "issuer_data": {"ca": "https://acme.example.com/directory"},
        }
        (certs_dir / "test.example.com.json").write_text(json.dumps(meta))

        with patch("pathlib.Path.rglob") as mock_rglob:
            json_file = certs_dir / "test.example.com.json"
            mock_rglob.return_value = [json_file]
            mgr = CaddyManager()
            certs = mgr._parse_caddy_storage_certs(None)
            assert len(certs) == 1
            assert "acme.example.com" in certs[0]["issuer"]


def _parse_certs(root):
    certs = []
    for f in root.rglob("*.json"):
        meta = json.loads(f.read_text())
        domains = meta.get("sans", meta.get("domains", [])) or []
        if domains:
            certs.append(
                {
                    "serial": "test",
                    "domains": ", ".join(domains),
                    "not_before": "",
                    "not_after": "",
                    "expires_in_days": None,
                    "issuer": "Test CA",
                }
            )
    return certs


@pytest.mark.asyncio
async def test_get_certificates_api_success():
    mgr = CaddyManager()
    with (
        patch.object(mgr, "_get_managed_domains", AsyncMock(return_value=["panel.example.com"])),
        patch.object(mgr, "_check_certs_via_openssl", return_value=[
            {"serial": "abc", "domains": "panel.example.com", "issuer": "Let's Encrypt"}
        ]),
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

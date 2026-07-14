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


def test_save_api_token_new_file(tmp_path):
    mgr = CaddyManager()
    env_file = tmp_path / ".env"
    res = mgr.save_api_token("VAR", "TOKEN", str(env_file))
    assert res == " API token saved."
    assert env_file.read_text() == "VAR=TOKEN\n"


def test_save_api_token_existing_file(tmp_path):
    mgr = CaddyManager()
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=VAL\n")
    res = mgr.save_api_token("VAR", "TOKEN", str(env_file))
    assert res == " API token saved."
    assert env_file.read_text() == "OTHER=VAL\nVAR=TOKEN\n"


def test_save_api_token_existing_var(tmp_path):
    mgr = CaddyManager()
    env_file = tmp_path / ".env"
    env_file.write_text("VAR=OLD_TOKEN\n")
    res = mgr.save_api_token("VAR", "TOKEN", str(env_file))
    assert res == " API token saved."
    # Wait, it checks `safe_api_var not in content`, so it doesn't write if present
    assert env_file.read_text() == "VAR=OLD_TOKEN\n"


def test_save_api_token_permission_error():
    mgr = CaddyManager()
    # Path that shouldn't be writable
    res = mgr.save_api_token(
        "VAR", "TOKEN", "/root/some_file_that_doesnt_exist_and_cant_be_written"
    )
    assert res == " (API token not saved — set manually in /etc/caddy/.env)"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.asyncio.create_subprocess_exec")
async def test_generate_and_reload_success(mock_exec, tmp_path):
    mgr = CaddyManager()

    # Mock for caddy validate
    mock_validate = AsyncMock()
    mock_validate.communicate.return_value = (b"", b"")
    mock_validate.returncode = 0

    # Mock for systemctl reload
    mock_reload = AsyncMock()
    mock_reload.communicate.return_value = (b"", b"")
    mock_reload.returncode = 0

    mock_exec.side_effect = [mock_validate, mock_reload]

    caddyfile_path = tmp_path / "Caddyfile"
    res = await mgr.generate_and_reload("test content", str(caddyfile_path))

    assert res == "Config loaded. Caddy will provision SSL certificates now."
    assert caddyfile_path.read_text() == "test content"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.asyncio.create_subprocess_exec")
async def test_generate_and_reload_validate_fails(mock_exec):
    mgr = CaddyManager()

    mock_validate = AsyncMock()
    mock_validate.communicate.return_value = (b"", b"Syntax error")
    mock_validate.returncode = 1
    mock_exec.return_value = mock_validate

    res = await mgr.generate_and_reload("bad content")
    assert res == "Caddy validation failed: Syntax error"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.asyncio.create_subprocess_exec")
async def test_generate_and_reload_validate_not_found(mock_exec, tmp_path):
    mgr = CaddyManager()

    # Simulate FileNotFoundError for caddy validate
    mock_exec.side_effect = [
        FileNotFoundError(),
        AsyncMock(communicate=AsyncMock(return_value=(b"", b"")), returncode=0),
    ]

    caddyfile_path = tmp_path / "Caddyfile"
    res = await mgr.generate_and_reload("content", str(caddyfile_path))
    assert res == "Config loaded. Caddy will provision SSL certificates now."


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.asyncio.create_subprocess_exec")
async def test_generate_and_reload_reload_fails(mock_exec, tmp_path):
    mgr = CaddyManager()

    mock_validate = AsyncMock()
    mock_validate.communicate.return_value = (b"", b"")
    mock_validate.returncode = 0

    mock_reload = AsyncMock()
    mock_reload.communicate.return_value = (b"", b"Reload error")
    mock_reload.returncode = 1

    mock_exec.side_effect = [mock_validate, mock_reload]

    caddyfile_path = tmp_path / "Caddyfile"
    res = await mgr.generate_and_reload("content", str(caddyfile_path))
    assert res == "Caddy reload failed: Reload error"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_generate_and_reload_permission_error():
    mgr = CaddyManager()
    # Try to write to root
    res = await mgr.generate_and_reload("content", "/root/Caddyfile")
    assert "Cannot write Caddyfile — permission denied" in res or "Caddy config error" in res


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.httpx.AsyncClient")
async def test_get_managed_domains_success(mock_client_class):
    from unittest.mock import MagicMock

    mgr = CaddyManager()

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(
        return_value={"srv1": {"routes": [{"match": [{"host": ["domain1.com", "domain2.com"]}]}]}}
    )
    mock_client.get.return_value = mock_resp
    mock_client_class.return_value.__aenter__.return_value = mock_client

    domains = await mgr._get_managed_domains()
    assert domains == ["domain1.com", "domain2.com"]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.httpx.AsyncClient")
async def test_get_managed_domains_not_200(mock_client_class):
    mgr = CaddyManager()

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 500
    mock_client.get.return_value = mock_resp
    mock_client_class.return_value.__aenter__.return_value = mock_client

    domains = await mgr._get_managed_domains()
    assert domains == []


def test_check_certs_via_openssl_success():
    mgr = CaddyManager()
    with patch("socket.create_connection"), patch("ssl.create_default_context") as mock_ctx:
        mock_ssock = mock_ctx.return_value.wrap_socket.return_value.__enter__.return_value
        mock_ssock.getpeercert.return_value = {
            "serialNumber": "123",
            "notBefore": "some time",
            "notAfter": "Feb 23 12:00:00 2025 GMT",
            "issuer": [(("O", "Let's Encrypt"),)],
        }

        with patch("ssl.cert_time_to_seconds", return_value=1740312000.0):
            res = mgr._check_certs_via_openssl(["example.com"])
            assert len(res) == 1
            assert res[0]["domains"] == "example.com"
            assert res[0]["serial"] == "123"
            assert res[0]["issuer"] == "O=Let's Encrypt"


def test_check_certs_via_openssl_exception():
    mgr = CaddyManager()
    with patch("socket.create_connection", side_effect=Exception("socket error")):
        res = mgr._check_certs_via_openssl(["example.com"])
        assert res == []


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.httpx.AsyncClient")
async def test_renew_certificate_success(mock_client_class):
    from unittest.mock import MagicMock

    mgr = CaddyManager()

    mock_client = AsyncMock()
    mock_resp1 = AsyncMock()
    mock_resp1.status_code = 200
    mock_resp1.json = MagicMock(return_value={"config": "test"})

    mock_resp2 = AsyncMock()
    mock_resp2.raise_for_status = MagicMock()

    mock_client.get.return_value = mock_resp1
    mock_client.post.return_value = mock_resp2
    mock_client_class.return_value.__aenter__.return_value = mock_client

    res = await mgr.renew_certificate("example.com")
    assert res["success"] is True


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.httpx.AsyncClient")
async def test_renew_certificate_get_fails(mock_client_class):
    mgr = CaddyManager()

    mock_client = AsyncMock()
    mock_resp1 = AsyncMock()
    mock_resp1.status_code = 500

    mock_client.get.return_value = mock_resp1
    mock_client_class.return_value.__aenter__.return_value = mock_client

    res = await mgr.renew_certificate("example.com")
    assert res["success"] is False


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.httpx.AsyncClient")
async def test_renew_certificate_exception(mock_client_class):
    mgr = CaddyManager()

    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("network error")
    mock_client_class.return_value.__aenter__.return_value = mock_client

    res = await mgr.renew_certificate("example.com")
    assert res["success"] is False


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("pit_panel.core.caddy.CaddyManager.get_certificates")
@patch("pit_panel.core.caddy.CaddyManager.renew_certificate")
async def test_auto_renew_certificates(mock_renew, mock_get_certs):
    mgr = CaddyManager()

    mock_get_certs.return_value = [
        {"domains": "expiring.com", "expires_in_days": 10},
        {"domains": "ok.com", "expires_in_days": 30},
    ]
    mock_renew.return_value = {"success": True}

    res = await mgr.auto_renew_certificates(renew_days=14)
    assert len(res) == 1
    mock_renew.assert_called_once_with("expiring.com")

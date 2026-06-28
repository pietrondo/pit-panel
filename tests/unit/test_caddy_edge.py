from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pit_panel.core.caddy import CaddyManager


@pytest.mark.asyncio
async def test_get_certificates_api_exception():
    mgr = CaddyManager()
    with patch("httpx.AsyncClient") as mock_client:
        client = mock_client.return_value.__aenter__.return_value
        client.get = AsyncMock(side_effect=Exception("API failure"))
        certs = await mgr.get_certificates()
        assert certs == []


@pytest.mark.asyncio
async def test_renew_certificate_timeout():
    mgr = CaddyManager()
    with patch("httpx.AsyncClient") as mock_client:
        client = mock_client.return_value.__aenter__.return_value
        client.get = AsyncMock(side_effect=Exception("Timeout reading config"))
        result = await mgr.renew_certificate("example.com")
        assert result["success"] is False
        assert result["domain"] == "example.com"
        assert "Timeout reading config" in result["error"]


@pytest.mark.asyncio
async def test_renew_certificate_post_exception():
    mgr = CaddyManager()
    with patch("httpx.AsyncClient") as mock_client:
        from unittest.mock import Mock

        mock_get_resp = Mock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"config": "val"}
        client = mock_client.return_value.__aenter__.return_value
        client.get = AsyncMock(return_value=mock_get_resp)
        client.post = AsyncMock(side_effect=Exception("POST failure"))

        result = await mgr.renew_certificate("example.com")
        assert result["success"] is False
        assert result["domain"] == "example.com"
        assert "POST failure" in result["error"]


@pytest.mark.asyncio
async def test_renew_certificate_post_raise_for_status():
    mgr = CaddyManager()
    with patch("httpx.AsyncClient") as mock_client:
        from unittest.mock import Mock

        mock_get_resp = Mock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"config": "val"}
        client = mock_client.return_value.__aenter__.return_value
        client.get = AsyncMock(return_value=mock_get_resp)

        from unittest.mock import Mock

        mock_post_resp = Mock()
        mock_post_resp.raise_for_status.side_effect = Exception("HTTP 500")
        client.post = AsyncMock(return_value=mock_post_resp)

        result = await mgr.renew_certificate("example.com")
        assert result["success"] is False
        assert result["domain"] == "example.com"
        assert "HTTP 500" in result["error"]


def test_parse_caddy_storage_certs_rglob_exception():
    mgr = CaddyManager()
    with patch("pathlib.Path.rglob", side_effect=Exception("Permission denied reading directory")):
        certs = mgr._parse_caddy_storage_certs(None)
        assert certs == []


def test_parse_caddy_storage_certs_subprocess_exception(tmp_path):
    mgr = CaddyManager()
    certs_dir = tmp_path / "acme" / "example.com"
    certs_dir.mkdir(parents=True)
    import json

    meta = {"sans": ["example.com"]}
    (certs_dir / "example.com.json").write_text(json.dumps(meta))
    (certs_dir / "example.com.crt").write_text("fake crt")

    with (
        patch("pathlib.Path.rglob", return_value=[certs_dir / "example.com.json"]),
        patch("subprocess.run", side_effect=Exception("openssl command failed")),
    ):
        certs = mgr._parse_caddy_storage_certs(None)
        assert len(certs) == 1
        assert certs[0]["domains"] == "example.com"
        # It should gracefully fallback to metadata if subprocess fails
        assert certs[0]["not_after"] == ""


@pytest.mark.asyncio
async def test_generate_and_reload_permission_error():
    mgr = CaddyManager()
    with patch("pathlib.Path.write_text", side_effect=PermissionError("Permission denied")):
        result = await mgr.generate_and_reload("config content")
        assert result == "Cannot write Caddyfile — permission denied."


@pytest.mark.asyncio
async def test_generate_and_reload_subprocess_failure():
    mgr = CaddyManager()
    with patch("pathlib.Path.write_text"), patch("pathlib.Path.mkdir"):
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = (b"", b"systemctl error")
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await mgr.generate_and_reload("config content")
            assert "Caddy reload failed: systemctl error" in result


@pytest.mark.asyncio
async def test_generate_and_reload_exception():
    mgr = CaddyManager()
    with patch("pathlib.Path.mkdir", side_effect=Exception("Unknown error")):
        result = await mgr.generate_and_reload("config content")
        assert "Caddy config error: Unknown error" in result


def test_read_file_safely_permission_error_fallback_success():
    mgr = CaddyManager()
    mock_path = MagicMock()
    mock_path.read_text.side_effect = PermissionError("Permission denied")

    from unittest.mock import Mock

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "sudo file content\n"

    with patch("subprocess.run", return_value=mock_result):
        content = mgr._read_file_safely(mock_path)
        assert content == "sudo file content"


def test_read_file_safely_permission_error_fallback_failure():
    mgr = CaddyManager()
    mock_path = MagicMock()
    mock_path.read_text.side_effect = PermissionError("Permission denied")

    with patch("subprocess.run", side_effect=Exception("sudo error")):
        content = mgr._read_file_safely(mock_path)
        assert content == ""

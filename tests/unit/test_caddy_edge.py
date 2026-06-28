from unittest.mock import AsyncMock, patch

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

        async def mock_exec(*args, **kwargs):
            proc = AsyncMock()
            if args[0] == "caddy":
                proc.returncode = 0
                proc.communicate.return_value = (b"ok", b"")
            else:
                proc.returncode = 1
                proc.communicate.return_value = (b"", b"systemctl error")
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await mgr.generate_and_reload("config content")
            assert "Caddy reload failed: systemctl error" in result


@pytest.mark.asyncio
async def test_generate_and_reload_validation_failure():
    mgr = CaddyManager()
    with patch("pathlib.Path.write_text"), patch("pathlib.Path.mkdir"):
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = (b"", b"Caddyfile syntax error")
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await mgr.generate_and_reload("config content")
            assert "Caddy validation failed: Caddyfile syntax error" in result


@pytest.mark.asyncio
async def test_generate_and_reload_success():
    mgr = CaddyManager()
    with patch("pathlib.Path.write_text"), patch("pathlib.Path.mkdir"):

        async def mock_exec(*args, **kwargs):
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate.return_value = (b"", b"")
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await mgr.generate_and_reload("config content")
            assert "Config loaded. Caddy will provision SSL certificates now." in result


@pytest.mark.asyncio
async def test_generate_and_reload_exception():
    mgr = CaddyManager()
    with patch("pathlib.Path.mkdir", side_effect=Exception("Unknown error")):
        result = await mgr.generate_and_reload("config content")
        assert "Caddy config error: Unknown error" in result

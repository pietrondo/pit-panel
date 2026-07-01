import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from pit_panel.web.routes.debug_api import _run, _verify_token


@pytest.mark.asyncio
async def test_verify_token_missing():
    with pytest.raises(HTTPException) as exc:
        _verify_token(None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing X-Debug-Token header"


@pytest.mark.asyncio
async def test_verify_token_not_configured(monkeypatch, tmp_path):
    mock_settings = MagicMock()
    mock_settings.debug_token_path = str(tmp_path / "missing_token")
    monkeypatch.setattr("pit_panel.web.routes.debug_api.get_settings", lambda: mock_settings)

    with pytest.raises(HTTPException) as exc:
        _verify_token("sometoken")
    assert exc.value.status_code == 503
    assert exc.value.detail == "Debug token not configured on this server"


@pytest.mark.asyncio
async def test_verify_token_invalid(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("expected_token\n")
    mock_settings = MagicMock()
    mock_settings.debug_token_path = str(token_file)
    monkeypatch.setattr("pit_panel.web.routes.debug_api.get_settings", lambda: mock_settings)

    with pytest.raises(HTTPException) as exc:
        _verify_token("invalid_token")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Invalid debug token"


@pytest.mark.asyncio
async def test_verify_token_success(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("expected_token\n")
    mock_settings = MagicMock()
    mock_settings.debug_token_path = str(token_file)
    monkeypatch.setattr("pit_panel.web.routes.debug_api.get_settings", lambda: mock_settings)

    token = _verify_token("expected_token")
    assert token == "expected_token"


@pytest.mark.asyncio
async def test_run_success(monkeypatch):
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"stdout ", b"stderr")
    mock_create = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create)

    res = await _run(["ls"])
    assert res == "stdout stderr"


@pytest.mark.asyncio
async def test_run_empty(monkeypatch):
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"   ")
    mock_create = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create)

    res = await _run(["ls"])
    assert res == "(empty)"


@pytest.mark.asyncio
async def test_run_exception(monkeypatch):
    mock_create = AsyncMock(side_effect=Exception("mocked error"))
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create)

    res = await _run(["ls"])
    assert res == "ERROR: mocked error"

@pytest.mark.asyncio
async def test_run_timeout(monkeypatch):
    mock_proc = AsyncMock()
    mock_proc.kill = MagicMock()
    mock_proc.communicate.side_effect = [asyncio.TimeoutError, (b"", b"")]
    mock_create = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create)

    res = await _run(["ls"], timeout=5)
    assert res == "ERROR: Command timed out after 5 seconds"
    mock_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_debug_logs(monkeypatch):
    mock_run = AsyncMock(return_value="logs output")
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_logs

    mock_req = MagicMock(spec=Request)
    res = await debug_logs(mock_req, lines=10, priority="error", token="tok")

    assert isinstance(res, PlainTextResponse)
    assert res.body == b"logs output"
    mock_run.assert_called_once_with(
        ["journalctl", "-u", "-p", "pit-panel.service", "-n", "10", "--no-pager"]
    )


@pytest.mark.asyncio
async def test_debug_logs_info(monkeypatch):
    mock_run = AsyncMock(return_value="logs output info")
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_logs

    mock_req = MagicMock(spec=Request)
    res = await debug_logs(mock_req, lines=10, priority="info", token="tok")

    assert isinstance(res, PlainTextResponse)
    assert res.body == b"logs output info"
    mock_run.assert_called_once_with(
        ["journalctl", "-u", "pit-panel.service", "-n", "10", "--no-pager"]
    )


@pytest.mark.asyncio
async def test_debug_certs(monkeypatch):
    mock_req = MagicMock(spec=Request)

    mock_caddy_manager_instance = AsyncMock()
    mock_caddy_manager_instance.get_certificates.return_value = {"cert": "data"}
    mock_caddy_manager = MagicMock(return_value=mock_caddy_manager_instance)
    monkeypatch.setattr("pit_panel.web.routes.debug_api.CaddyManager", mock_caddy_manager)

    mock_settings = MagicMock()
    mock_settings.caddy_admin_url = "http://caddy"
    monkeypatch.setattr("pit_panel.web.routes.debug_api.get_settings", lambda: mock_settings)

    from pit_panel.web.routes.debug_api import debug_certs

    res = await debug_certs(mock_req, token="tok")

    assert isinstance(res, JSONResponse)
    assert json.loads(res.body) == {"cert": "data"}
    mock_caddy_manager.assert_called_once_with("http://caddy")
    mock_caddy_manager_instance.get_certificates.assert_called_once()


@pytest.mark.asyncio
async def test_debug_system(monkeypatch, tmp_path):
    mock_req = MagicMock(spec=Request)

    mock_settings = MagicMock()
    mock_settings.config_path = "config"
    mock_settings.data_dir = "data"
    mock_settings.debug_token_path = str(tmp_path / "tok")
    mock_settings.panel_url = "url"
    mock_settings.effective_domain = "domain"
    mock_settings.git_remote = "remote"
    mock_settings.git_branch = "branch"
    monkeypatch.setattr("pit_panel.web.routes.debug_api.get_settings", lambda: mock_settings)

    mock_run = AsyncMock(return_value="cmd_out")
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    monkeypatch.setattr("platform.python_version", lambda: "3.x")
    monkeypatch.setattr("platform.node", lambda: "host")
    monkeypatch.setattr("os.getcwd", lambda: "/cwd")

    from pit_panel.web.routes.debug_api import debug_system

    res = await debug_system(mock_req, token="tok")

    assert isinstance(res, JSONResponse)
    body = json.loads(res.body)
    assert body["python"] == "3.x"
    assert body["hostname"] == "host"
    assert body["cwd"] == "/cwd"
    assert body["config_path"] == "config"
    assert body["data_dir"] == "data"
    assert not body["debug_token_exists"]
    assert body["panel_url"] == "url"
    assert body["effective_domain"] == "domain"
    assert body["git_remote"] == "remote"
    assert body["git_branch"] == "branch"
    assert body["disk_free_gb"] == "cmd_out"
    assert body["uptime"] == "cmd_out"
    assert body["memory"] == "cmd_out"

    assert mock_run.call_count == 3

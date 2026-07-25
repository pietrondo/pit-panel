import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from pit_panel.web.routes.debug_api import (
    _CONTAINER_RE,
    _audit,
    _run,
    _verify_token,
)


@pytest.fixture
def tmp_audit(monkeypatch, tmp_path):
    log = tmp_path / "debug-audit.log"
    monkeypatch.setattr("pit_panel.web.routes.debug_api._AUDIT_LOG_PATH", str(log))
    return log


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
async def test_verify_token_empty_file(monkeypatch, tmp_path):
    """Empty file must still 503, not silently accept."""
    token_file = tmp_path / "token"
    token_file.write_text("\n")
    mock_settings = MagicMock()
    mock_settings.debug_token_path = str(token_file)
    monkeypatch.setattr("pit_panel.web.routes.debug_api.get_settings", lambda: mock_settings)

    with pytest.raises(HTTPException) as exc:
        _verify_token("any")
    assert exc.value.status_code == 503


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
    assert "timestamp" in body
    assert isinstance(body["timestamp"], int)

    assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_debug_errors(monkeypatch):
    mock_run = AsyncMock(return_value="errs")
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_errors

    mock_req = MagicMock(spec=Request)
    res = await debug_errors(mock_req, lines=50, token="tok")

    assert isinstance(res, PlainTextResponse)
    assert res.body == b"errs"
    args = mock_run.call_args[0][0]
    assert args[0] == "journalctl"
    assert "-p" in args
    assert "err" in args


@pytest.mark.asyncio
async def test_debug_errors_clamps_lines(monkeypatch):
    mock_run = AsyncMock(return_value="x")
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_errors

    mock_req = MagicMock(spec=Request)
    await debug_errors(mock_req, lines=9999999, token="tok")
    args = mock_run.call_args[0][0]
    assert str(2000) in args


@pytest.mark.asyncio
async def test_debug_caddy_logs(monkeypatch):
    mock_run = AsyncMock(return_value="caddy log")
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_caddy_logs

    mock_req = MagicMock(spec=Request)
    res = await debug_caddy_logs(mock_req, lines=100, token="tok")

    assert isinstance(res, PlainTextResponse)
    args = mock_run.call_args[0][0]
    assert args[0] == "journalctl"
    assert "caddy" in args
    assert str(100) in args


@pytest.mark.asyncio
async def test_debug_docker_ps(monkeypatch):
    sample = (
        '{"Names":"web","State":"running","Status":"Up"}\n'
        '{"Names":"db","State":"exited","Status":"Exited (1) 5 minutes ago"}\n'
    )
    mock_run = AsyncMock(return_value=sample)
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_docker_ps

    mock_req = MagicMock(spec=Request)
    res = await debug_docker_ps(mock_req, token="tok")

    assert isinstance(res, JSONResponse)
    body = json.loads(res.body)
    assert len(body["containers"]) == 2
    assert body["containers"][0]["Names"] == "web"
    assert body["raw"] == sample


@pytest.mark.asyncio
async def test_debug_docker_logs_validates_container_name():
    from pit_panel.web.routes.debug_api import debug_docker_logs

    mock_req = MagicMock(spec=Request)
    with pytest.raises(HTTPException) as exc:
        await debug_docker_logs(mock_req, container="bad;name|rm -rf", lines=10, token="tok")
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "name",
    ["web", "nginx-prod_1", "container.dev-1", "a", "A1.b-c"],
)
def test_container_name_accepts_valid(name):
    assert _CONTAINER_RE.match(name)


@pytest.mark.parametrize(
    "name",
    ["", "-bad", "a;rm", "a b", "a/b", "a$b", "a|b", "a" * 65],
)
def test_container_name_rejects_invalid(name):
    assert not _CONTAINER_RE.match(name)


@pytest.mark.asyncio
async def test_debug_docker_logs_calls_command(monkeypatch):
    mock_run = AsyncMock(return_value="container logs")
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_docker_logs

    mock_req = MagicMock(spec=Request)
    res = await debug_docker_logs(mock_req, container="nginx", lines=50, token="tok")

    assert isinstance(res, PlainTextResponse)
    args = mock_run.call_args[0][0]
    assert args == ["docker", "logs", "--tail", "50", "nginx"]


@pytest.mark.asyncio
async def test_debug_upstreams_returns_payload(monkeypatch):
    import httpx

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"upstreams": [{"address": "127.0.0.1:8080", "healthy": True}]}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout: _Client())

    mock_settings = MagicMock()
    mock_settings.caddy_admin_url = "http://127.0.0.1:2019/"
    monkeypatch.setattr("pit_panel.web.routes.debug_api.get_settings", lambda: mock_settings)

    from pit_panel.web.routes.debug_api import debug_upstreams

    mock_req = MagicMock(spec=Request)
    res = await debug_upstreams(mock_req, token="tok")

    assert isinstance(res, JSONResponse)
    assert json.loads(res.body) == {
        "upstreams": [{"address": "127.0.0.1:8080", "healthy": True}]
    }


@pytest.mark.asyncio
async def test_audit_writes_line_without_token(tmp_audit):
    req = MagicMock(spec=Request)
    req.client.host = "1.2.3.4"
    req.method = "GET"
    req.url.path = "/api/debug/system"

    _audit(req, req.url.path, 200)

    content = tmp_audit.read_text()
    assert "ip=1.2.3.4" in content
    assert "/api/debug/system" in content
    assert "status=200" in content
    assert "tok" not in content
    assert "X-Debug-Token" not in content


@pytest.mark.asyncio
async def test_audit_falls_back_to_tmp_when_primary_unwritable(monkeypatch, tmp_path):
    """If /var/log/pit-panel is read-only (e.g. EACCES), audit must fall back
    to a writable location (e.g. /tmp) instead of silently losing the entry."""
    import os as _os

    primary = tmp_path / "primary" / "debug-audit.log"
    fallback = tmp_path / "fallback" / "debug-audit.log"

    monkeypatch.setattr("pit_panel.web.routes.debug_api._AUDIT_LOG_PATH", str(primary))
    monkeypatch.setattr("pit_panel.web.routes.debug_api._AUDIT_FALLBACK_PATH", str(fallback))

    real_open = _os.open
    real_mkdir = _os.mkdir

    def fake_open(path, *args, **kwargs):
        if str(path) == str(primary):
            raise PermissionError("read-only filesystem")
        return real_open(path, *args, **kwargs)

    def fake_mkdir(path, *args, **kwargs):
        if str(path) == str(primary.parent):
            raise PermissionError("read-only filesystem")
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr("os.open", fake_open)
    monkeypatch.setattr("os.mkdir", fake_mkdir)

    req = MagicMock(spec=Request)
    req.client.host = "9.9.9.9"
    req.method = "GET"
    req.url.path = "/api/debug/system"

    _audit(req, req.url.path, 200)

    assert fallback.exists(), f"fallback file not created at {fallback}"
    content = fallback.read_text()
    assert "ip=9.9.9.9" in content
    assert "/api/debug/system" in content


@pytest.mark.asyncio
async def test_audit_swallows_total_failure_without_raising(monkeypatch, tmp_path, caplog):
    """If both primary and fallback fail, _audit must NOT raise. It logs a
    warning and returns. The request handler must continue normally."""

    primary = tmp_path / "primary" / "debug-audit.log"
    fallback = tmp_path / "fallback" / "debug-audit.log"

    monkeypatch.setattr("pit_panel.web.routes.debug_api._AUDIT_LOG_PATH", str(primary))
    monkeypatch.setattr("pit_panel.web.routes.debug_api._AUDIT_FALLBACK_PATH", str(fallback))

    def always_fail(*args, **kwargs):
        raise OSError("disk on fire")

    monkeypatch.setattr("os.open", always_fail)
    monkeypatch.setattr("os.mkdir", always_fail)

    req = MagicMock(spec=Request)
    req.client.host = "1.1.1.1"
    req.method = "GET"
    req.url.path = "/api/debug/system"

    with caplog.at_level("WARNING"):
        _audit(req, req.url.path, 200)  # must not raise

    assert any("debug_audit_log_failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_debug_audit_reads_back(tmp_audit):
    tmp_audit.parent.mkdir(parents=True, exist_ok=True)
    tmp_audit.write_text("2026-07-25T13:00:00Z ip=5.6.7.8 path=/api/debug/system status=200\n")

    mock_req = MagicMock(spec=Request)
    monkeypatch_audit_path = tmp_audit
    import pit_panel.web.routes.debug_api as mod

    orig_path = mod._AUDIT_LOG_PATH
    mod._AUDIT_LOG_PATH = str(monkeypatch_audit_path)
    try:
        res = await mod.debug_audit(mock_req, lines=10, token="tok")
    finally:
        mod._AUDIT_LOG_PATH = orig_path

    assert isinstance(res, PlainTextResponse)
    assert b"ip=5.6.7.8" in res.body


@pytest.mark.asyncio
async def test_debug_audit_missing_file(monkeypatch, tmp_path):
    log = tmp_path / "nope.log"
    monkeypatch.setattr(
        "pit_panel.web.routes.debug_api._AUDIT_LOG_PATH", str(log)
    )

    from pit_panel.web.routes.debug_api import debug_audit

    mock_req = MagicMock(spec=Request)
    res = await debug_audit(mock_req, lines=10, token="tok")
    assert b"(no audit entries yet)" in res.body


@pytest.mark.asyncio
async def test_debug_docker_stats_all(monkeypatch):
    sample = (
        '{"Name":"wiki-wikijs-1","CPUPerc":"12.34%","MemUsage":"450MiB / 1.9GiB",'
        '"MemPerc":"23.15%","NetIO":"1.2MB / 800kB","BlockIO":"5MB / 2MB","PIDs":"18"}\n'
        '{"Name":"blog-wordpress-1","CPUPerc":"0.50%","MemUsage":"120MiB / 1.9GiB",'
        '"MemPerc":"6.20%","NetIO":"100kB / 50kB","BlockIO":"1MB / 0B","PIDs":"9"}\n'
    )
    mock_run = AsyncMock(return_value=sample)
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_docker_stats

    mock_req = MagicMock(spec=Request)
    res = await debug_docker_stats(mock_req, token="tok")

    assert isinstance(res, JSONResponse)
    body = json.loads(res.body)
    assert len(body["stats"]) == 2
    assert body["stats"][0]["name"] == "wiki-wikijs-1"
    assert body["stats"][0]["cpu"] == "12.34%"
    assert body["stats"][0]["mem"] == "450MiB / 1.9GiB"
    assert body["stats"][1]["name"] == "blog-wordpress-1"
    args = mock_run.call_args[0][0]
    assert args == ["docker", "stats", "--no-stream", "--format", "{{json .}}"]


@pytest.mark.asyncio
async def test_debug_docker_stats_single_container(monkeypatch):
    sample = (
        '{"Name":"wiki-wikijs-1","CPUPerc":"12.34%","MemUsage":"450MiB / 1.9GiB",'
        '"MemPerc":"23.15%","NetIO":"1.2MB / 800kB","BlockIO":"5MB / 2MB","PIDs":"18"}\n'
    )
    mock_run = AsyncMock(return_value=sample)
    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", mock_run)

    from pit_panel.web.routes.debug_api import debug_docker_stats

    mock_req = MagicMock(spec=Request)
    res = await debug_docker_stats(mock_req, container="wiki-wikijs-1", token="tok")

    assert isinstance(res, JSONResponse)
    body = json.loads(res.body)
    assert body["stats"][0]["name"] == "wiki-wikijs-1"
    args = mock_run.call_args[0][0]
    assert "wiki-wikijs-1" in args
    assert "--no-trunc" in args


@pytest.mark.asyncio
async def test_debug_docker_stats_validates_container_name():
    from pit_panel.web.routes.debug_api import debug_docker_stats

    mock_req = MagicMock(spec=Request)
    with pytest.raises(HTTPException) as exc:
        await debug_docker_stats(mock_req, container="bad;name|rm -rf", token="tok")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_debug_doctor_aggregates_health(monkeypatch):
    """One GET that returns: system, upstreams, last-errors, audit-count."""
    monkeypatch.setattr(
        "pit_panel.web.routes.debug_api._AUDIT_LOG_PATH",
        "/tmp/doctor-test.log",
    )
    Path("/tmp/doctor-test.log").write_text(
        "2026-07-25T10:00:00Z ip=1.1.1.1 method=GET path=/api/debug/system status=200\n"
        "2026-07-25T10:00:01Z ip=1.1.1.1 method=GET path=/api/debug/errors status=200\n"
    )

    async def fake_run(cmd, timeout=10, cwd=None):
        if cmd[:2] == ["df", "-h"]:
            return "        20G"
        if cmd[:1] == ["uptime"]:
            return "up 1 day"
        if cmd[:1] == ["free"]:
            return "total 1.9Gi used 1.4Gi"
        if cmd[:2] == ["journalctl", "-p"]:
            return "Jul 25 10:00:00 host sshd[1]: error"
        return ""

    monkeypatch.setattr("pit_panel.web.routes.debug_api._run", fake_run)

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"upstreams": [{"address": "127.0.0.1:8080", "healthy": True}]}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp()

    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", lambda timeout: _Client())

    from pit_panel.web.routes.debug_api import debug_doctor

    mock_req = MagicMock(spec=Request)
    res = await debug_doctor(mock_req, token="tok")

    assert isinstance(res, JSONResponse)
    body = json.loads(res.body)
    assert "system" in body
    assert "upstreams" in body
    assert "last_errors" in body
    assert body["audit_count"] == 2
    assert body["upstreams"]["upstreams"][0]["healthy"] is True
    assert "Jul 25" in body["last_errors"]

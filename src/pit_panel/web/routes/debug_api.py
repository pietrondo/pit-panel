"""Secret debug API — logs, certs, system info, file ops. Protected by token file.

Every request is appended to an audit log that NEVER contains the token value.
File operations are restricted to /opt/pit-panel and /etc/pit-panel.
"""

import asyncio
import contextlib
import json
import logging
import os
import platform
import re
import secrets
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, PlainTextResponse

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.sudo_ops import run_cmd
from pit_panel.web.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter()

_AUDIT_LOG_PATH = "/var/log/pit-panel/debug-audit.log"
_AUDIT_FALLBACK_PATH = str(Path(tempfile.gettempdir()) / "pit-panel-debug-audit.log")
_GRACE_PATH = "/etc/pit-panel/debug_token.grace"
_MIN_TOKEN_LEN = 16
_DEFAULT_GRACE_SECONDS = 3600
_MAX_GRACE_SECONDS = 86400

_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _verify_token(x_debug_token: str | None = Header(None)) -> str:
    import secrets

    if not x_debug_token:
        raise HTTPException(status_code=401, detail="Missing X-Debug-Token header")
    token_path = Path(get_settings().debug_token_path)
    if not token_path.exists():
        raise HTTPException(status_code=503, detail="Debug token not configured on this server")
    expected = token_path.read_text().strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Debug token not configured on this server")
    if secrets.compare_digest(x_debug_token.encode("utf-8"), expected.encode("utf-8")):
        return x_debug_token

    # Primary didn't match. Fall through to grace-period check.
    grace_path = Path(_GRACE_PATH)
    if grace_path.exists():
        try:
            grace = json.loads(grace_path.read_text())
            old = (grace.get("old_token") or "").strip()
            expires_at = float(grace.get("expires_at") or 0)
            if (
                old
                and expires_at > time.time()
                and secrets.compare_digest(x_debug_token.encode("utf-8"), old.encode("utf-8"))
            ):
                return x_debug_token
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    raise HTTPException(status_code=403, detail="Invalid debug token")


def _audit(request: Request, path: str, status: int) -> None:
    """Append an audit line. NEVER include the token value.

    Falls back to /tmp if the primary path is unwritable (read-only fs,
    EACCES on directory create, etc). Both failures are logged at WARNING
    level and swallowed; the request handler continues normally.
    """
    client_ip = request.client.host if request.client else "unknown"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} ip={client_ip} method={request.method} path={path} status={status}\n"
    encoded = line.encode("utf-8")

    for path_try in (_AUDIT_LOG_PATH, _AUDIT_FALLBACK_PATH):
        try:
            Path(path_try).parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                path_try,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            try:
                os.write(fd, encoded)
            finally:
                os.close(fd)
            return
        except Exception as e:
            logger.warning("debug_audit_log_failed path=%s err=%s", path_try, e)
            continue
    logger.warning("debug_audit_log_total_failure path=%s ip=%s", path, client_ip)


async def _run(cmd: list[str], timeout: int = 10, cwd: str | None = None) -> str:
    res = await run_cmd(cmd, timeout=timeout, cwd=cwd)
    if res.returncode == -1:
        if "timeout" in res.stderr.lower():
            return f"ERROR: Command timed out after {timeout} seconds"
        return f"ERROR: {res.stderr}"
    return (res.stdout + res.stderr).strip() or "(empty)"


@router.get("/api/debug/logs")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_logs(
    request: Request,
    lines: int = 50,
    priority: str = "info",
    token: str = Depends(_verify_token),
) -> PlainTextResponse:
    priority_flag = {"error": "-p", "warning": "-p", "info": ""}
    flag = priority_flag.get(priority, "")
    args = ["journalctl", "-u", "pit-panel.service", "-n", str(lines), "--no-pager"]
    if flag:
        args.insert(2, flag)
    body = await _run(args)
    _audit(request, request.url.path, 200)
    return PlainTextResponse(body)


@router.get("/api/debug/certs")  # type: ignore[untyped-decorator]
@limiter.limit("10/minute")
async def debug_certs(
    request: Request,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    caddy = CaddyManager(get_settings().caddy_admin_url)
    certs = await caddy.get_certificates()
    _audit(request, request.url.path, 200)
    return JSONResponse(certs)


@router.get("/api/debug/system")  # type: ignore[untyped-decorator]
@limiter.limit("10/minute")
async def debug_system(
    request: Request,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    s = get_settings()

    disk_free_gb, uptime, memory = await asyncio.gather(
        _run(["df", "-h", "/", "--output=avail", "--no-headers"]),
        _run(["uptime", "-p"]),
        _run(["free", "-h"]),
    )

    _audit(request, request.url.path, 200)
    return JSONResponse(
        {
            "python": platform.python_version(),
            "hostname": platform.node(),
            "cwd": os.getcwd(),
            "config_path": s.config_path,
            "data_dir": s.data_dir,
            "debug_token_exists": Path(s.debug_token_path).exists(),
            "panel_url": s.panel_url,
            "effective_domain": s.effective_domain,
            "git_remote": s.git_remote,
            "git_branch": s.git_branch,
            "disk_free_gb": disk_free_gb,
            "uptime": uptime,
            "memory": memory,
            "timestamp": int(time.time()),
        }
    )


@router.get("/api/debug/errors")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_errors(
    request: Request,
    lines: int = 200,
    token: str = Depends(_verify_token),
) -> PlainTextResponse:
    """Aggregate recent errors across all systemd units.

    Useful for diagnosing a 502: shows what blew up across caddy,
    pit-panel, docker, etc., in chronological order.
    """
    lines = max(1, min(int(lines), 2000))
    body = await _run(
        ["journalctl", "-p", "err", "--no-pager", "-n", str(lines)],
        timeout=15,
    )
    _audit(request, request.url.path, 200)
    return PlainTextResponse(body)


@router.get("/api/debug/caddy-logs")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_caddy_logs(
    request: Request,
    lines: int = 200,
    token: str = Depends(_verify_token),
) -> PlainTextResponse:
    lines = max(1, min(int(lines), 5000))
    body = await _run(
        ["journalctl", "-u", "caddy", "--no-pager", "-n", str(lines)],
        timeout=15,
    )
    _audit(request, request.url.path, 200)
    return PlainTextResponse(body)


@router.get("/api/debug/docker-ps")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_docker_ps(
    request: Request,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    out = await _run(
        ["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"],
        timeout=15,
    )
    containers = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        with contextlib.suppress(Exception):
            import json as _json

            containers.append(_json.loads(line))
    _audit(request, request.url.path, 200)
    return JSONResponse({"containers": containers, "raw": out})


@router.get("/api/debug/docker-logs")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_docker_logs(
    request: Request,
    container: str,
    lines: int = 100,
    token: str = Depends(_verify_token),
) -> PlainTextResponse:
    if not _CONTAINER_RE.match(container):
        raise HTTPException(status_code=400, detail="Invalid container name")
    lines = max(1, min(int(lines), 5000))
    body = await _run(
        ["docker", "logs", "--tail", str(lines), container],
        timeout=20,
    )
    _audit(request, request.url.path, 200)
    return PlainTextResponse(body)


@router.get("/api/debug/docker-stats")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_docker_stats(
    request: Request,
    container: str | None = None,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    """One-shot container resource snapshot. Read-only.

    Pass `container` to scope to one container; omit for all. The output is
    parsed from `docker stats --no-stream --format {{json .}}` so each entry
    is keyed by human-friendly names (name/cpu/mem/...) instead of the
    raw JSON keys.
    """
    import json as _json

    cmd = ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
    if container is not None:
        if not _CONTAINER_RE.match(container):
            raise HTTPException(status_code=400, detail="Invalid container name")
        cmd.insert(2, "--no-trunc")
        cmd.append(container)

    out = await _run(cmd, timeout=15)
    stats = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        with contextlib.suppress(Exception):
            raw = _json.loads(line)
            stats.append(
                {
                    "name": raw.get("Name") or raw.get("Names"),
                    "cpu": raw.get("CPUPerc"),
                    "mem": raw.get("MemUsage"),
                    "mem_pct": raw.get("MemPerc"),
                    "net": raw.get("NetIO"),
                    "block": raw.get("BlockIO"),
                    "pids": raw.get("PIDs"),
                }
            )
    _audit(request, request.url.path, 200)
    return JSONResponse({"stats": stats, "raw": out})


@router.get("/api/debug/upstreams")  # type: ignore[untyped-decorator]
@limiter.limit("10/minute")
async def debug_upstreams(
    request: Request,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    """Probe Caddy's reverse_proxy upstreams for 502 root-cause.

    Caddy admin API exposes runtime upstream health at
    /reverse_proxy/upstreams. If pit-panel upstream is marked unhealthy,
    that explains the 502.
    """
    import httpx

    admin_url = get_settings().caddy_admin_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{admin_url}/reverse_proxy/upstreams")
        payload = resp.json() if resp.status_code == 200 else {"error": resp.text}
        status = 200 if resp.status_code == 200 else 502
    except Exception as e:
        payload = {"error": str(e)}
        status = 502
    _audit(request, request.url.path, status)
    return JSONResponse(payload, status_code=status)


@router.get("/api/debug/audit")  # type: ignore[untyped-decorator]
@limiter.limit("10/minute")
async def debug_audit(
    request: Request,
    lines: int = 100,
    token: str = Depends(_verify_token),
) -> PlainTextResponse:
    """Read recent debug-API audit entries. NEVER includes the token value."""
    lines = max(1, min(int(lines), 2000))
    p = Path(_AUDIT_LOG_PATH)
    if not p.exists():
        body = "(no audit entries yet)"
    else:
        try:
            data = p.read_text(errors="replace").splitlines()[-lines:]
            body = "\n".join(data)
        except Exception as e:
            body = f"ERROR: {e}"
    _audit(request, request.url.path, 200)
    return PlainTextResponse(body)


@router.get("/api/debug/doctor")  # type: ignore[untyped-decorator]
@limiter.limit("5/minute")
async def debug_doctor(
    request: Request,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    """One-shot aggregate health check.

    Returns: system info, Caddy upstream health, last 20 error lines,
    audit-log line count. Designed for `pit-debug doctor` so the agent
    can spot regressions with a single call instead of 4.
    """
    import httpx

    s = get_settings()

    disk_free_gb, uptime_str, memory_str, last_errors = await asyncio.gather(
        _run(["df", "-h", "/", "--output=avail", "--no-headers"]),
        _run(["uptime", "-p"]),
        _run(["free", "-h"]),
        _run(
            ["journalctl", "-p", "err", "--no-pager", "-n", "20"],
            timeout=15,
        ),
    )

    upstreams: dict[str, Any] = {}
    try:
        admin = s.caddy_admin_url.rstrip("/")
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{admin}/reverse_proxy/upstreams")
        upstreams = resp.json() if resp.status_code == 200 else {"error": resp.text}
    except Exception as e:
        upstreams = {"error": str(e)}

    audit_count = 0
    try:
        p = Path(_AUDIT_LOG_PATH)
        if p.exists():
            audit_count = sum(1 for _ in p.open(errors="replace"))
    except Exception:
        pass

    _audit(request, request.url.path, 200)
    return JSONResponse(
        {
            "system": {
                "python": platform.python_version(),
                "hostname": platform.node(),
                "panel_url": s.panel_url,
                "disk_free_gb": disk_free_gb,
                "uptime": uptime_str,
                "memory": memory_str,
            },
            "upstreams": upstreams,
            "last_errors": last_errors,
            "audit_count": audit_count,
            "timestamp": int(time.time()),
        }
    )


@router.post("/api/debug/rotate-token")  # type: ignore[untyped-decorator]
@limiter.limit("3/minute")
async def rotate_debug_token(
    request: Request,
    payload: dict[str, Any],
    current_token: str = Depends(_verify_token),
) -> JSONResponse:
    """Rotate the debug token with a configurable grace period.

    Body: {"new_token": "...", "grace_seconds": 3600}

    The CURRENT token (this request's `X-Debug-Token`) MUST match the
    file on disk — this is the auth check, not a parameter. Caller is
    asking the server to trust a NEW value; the OLD value is preserved
    on disk in a sidecar so that any client that hasn't yet picked up
    the new token can still authenticate during the grace window.

    After `grace_seconds` the sidecar expires and the old token stops
    working. Default 1h, max 24h. New token must be >= 16 chars.
    """
    new_token = (payload.get("new_token") or "").strip()
    if len(new_token) < _MIN_TOKEN_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"new_token must be at least {_MIN_TOKEN_LEN} characters",
        )
    if secrets.compare_digest(new_token.encode("utf-8"), current_token.encode("utf-8")):
        raise HTTPException(
            status_code=400,
            detail="new_token must differ from current token",
        )

    grace = int(payload.get("grace_seconds") or _DEFAULT_GRACE_SECONDS)
    grace = max(0, min(grace, _MAX_GRACE_SECONDS))
    expires_at = int(time.time()) + grace

    token_path = Path(get_settings().debug_token_path)
    grace_path = Path(_GRACE_PATH)

    current_on_disk = token_path.read_text().strip() if token_path.exists() else ""
    if not current_on_disk:
        raise HTTPException(status_code=503, detail="Debug token not configured on this server")
    if not secrets.compare_digest(current_token.encode("utf-8"), current_on_disk.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid debug token (mid-rotation?)")

    grace_path.parent.mkdir(parents=True, exist_ok=True)
    grace_payload = json.dumps({"old_token": current_on_disk, "expires_at": expires_at})
    grace_fd = os.open(
        str(grace_path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        os.write(grace_fd, grace_payload.encode("utf-8"))
    finally:
        os.close(grace_fd)
    os.chmod(grace_path, 0o600)

    token_fd = os.open(
        str(token_path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        os.write(token_fd, (new_token + "\n").encode("utf-8"))
    finally:
        os.close(token_fd)
    os.chmod(token_path, 0o600)

    _audit(request, request.url.path, 200)
    return JSONResponse(
        {
            "new_token": new_token,
            "grace_expires_at": expires_at,
            "grace_seconds": grace,
        }
    )


_ALLOWED_PREFIXES = ("/opt/pit-panel", "/etc/pit-panel")


def _safe_path(raw: str) -> Path:
    p = Path(raw).resolve()
    if not any(
        p == Path(prefix).resolve() or p.is_relative_to(Path(prefix).resolve())
        for prefix in _ALLOWED_PREFIXES
    ):
        raise HTTPException(status_code=403, detail="Path outside allowed directories")
    return p


@router.get("/api/debug/ls")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_ls(
    request: Request,
    path: str = "/opt/pit-panel/apps",
    token: str = Depends(_verify_token),
) -> JSONResponse:
    resolved = _safe_path(path)
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")
    items = []
    for entry in sorted(resolved.iterdir()):
        try:
            st = entry.stat()
            items.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                    "size": st.st_size if not entry.is_dir() else 0,
                    "mtime": st.st_mtime,
                }
            )
        except OSError:
            continue
    _audit(request, request.url.path, 200)
    return JSONResponse({"path": str(resolved), "items": items})


@router.get("/api/debug/file")  # type: ignore[untyped-decorator]
@limiter.limit("30/minute")
async def debug_read_file(
    request: Request,
    path: str,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    resolved = _safe_path(path)
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if resolved.stat().st_size > 1_048_576:
        raise HTTPException(status_code=413, detail="File too large (max 1MB)")
    content = resolved.read_text(encoding="utf-8", errors="replace")
    _audit(request, request.url.path, 200)
    return JSONResponse({"path": str(resolved), "content": content})


@router.put("/api/debug/file")  # type: ignore[untyped-decorator]
@limiter.limit("20/minute")
async def debug_write_file(
    request: Request,
    payload: dict[str, Any],
    token: str = Depends(_verify_token),
) -> JSONResponse:
    raw_path = (payload.get("path") or "").strip()
    content = payload.get("content")
    if not raw_path or content is None:
        raise HTTPException(status_code=400, detail="path and content required")
    resolved = _safe_path(raw_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved.write_text(content, encoding="utf-8")
    except PermissionError as e:
        from pit_panel.core.sudo_ops import run_sudo

        sudo_pw = get_settings().sudo_password.strip()
        if not sudo_pw:
            raise HTTPException(
                status_code=500,
                detail="Permission denied and no sudo_password configured",
            ) from e
        import tempfile as _tf

        with _tf.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        await run_sudo(["/usr/bin/cp", tmp_path, str(resolved)], sudo_pw)
        await run_sudo(["/usr/bin/chmod", "644", str(resolved)], sudo_pw)
        os.unlink(tmp_path)
    _audit(request, request.url.path, 200)
    return JSONResponse({"status": "ok", "path": str(resolved), "bytes": len(content.encode())})


@router.post("/api/debug/mkdir")  # type: ignore[untyped-decorator]
@limiter.limit("20/minute")
async def debug_mkdir(
    request: Request,
    payload: dict[str, Any],
    token: str = Depends(_verify_token),
) -> JSONResponse:
    raw_path = (payload.get("path") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="path required")
    resolved = _safe_path(raw_path)
    resolved.mkdir(parents=True, exist_ok=True)
    _audit(request, request.url.path, 200)
    return JSONResponse({"status": "ok", "path": str(resolved)})


_COMPOSE_ACTIONS = {"up", "down", "restart", "pull", "logs"}


@router.post("/api/debug/update")  # type: ignore[untyped-decorator]
@limiter.limit("3/minute")
async def debug_update(
    request: Request,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    from pit_panel.core.sudo_ops import run_sudo

    sudo_pw = get_settings().sudo_password.strip()
    app_dir = "/opt/pit-panel"
    pull_out = await _run(["git", "pull", "--ff-only"], timeout=30, cwd=app_dir)
    if not sudo_pw:
        _audit(request, request.url.path, 200)
        return JSONResponse(
            {"status": "pulled", "output": pull_out, "restart": "skipped (no sudo_password)"}
        )
    restart_out = await run_sudo(["/usr/bin/systemctl", "restart", "pit-panel"], sudo_pw)
    _audit(request, request.url.path, 200)
    return JSONResponse({"status": "ok", "pull": pull_out, "restart": restart_out or "done"})


@router.post("/api/debug/compose")  # type: ignore[untyped-decorator]
@limiter.limit("10/minute")
async def debug_compose(
    request: Request,
    payload: dict[str, Any],
    token: str = Depends(_verify_token),
) -> JSONResponse:
    app = (payload.get("app") or "").strip()
    action = (payload.get("action") or "restart").strip()
    if not app or not re.fullmatch(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", app):
        raise HTTPException(status_code=400, detail="Invalid app name")
    if action not in _COMPOSE_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {_COMPOSE_ACTIONS}")

    app_dir = Path("/opt/pit-panel/apps") / app
    compose_file = app_dir / "docker-compose.yml"
    if not compose_file.exists():
        raise HTTPException(status_code=404, detail=f"No compose file for app '{app}'")

    cmd = ["docker", "compose", "-f", str(compose_file)]
    if action == "up":
        cmd += ["up", "-d"]
    elif action == "logs":
        cmd += ["logs", "--tail", "50"]
    else:
        cmd.append(action)

    out = await _run(cmd, timeout=30, cwd=str(app_dir))
    _audit(request, request.url.path, 200)
    return JSONResponse({"status": "ok", "app": app, "action": action, "output": out})


@router.websocket("/api/debug/tail")  # type: ignore[untyped-decorator]
async def tail_ws(
    websocket: WebSocket,
    service: str,
    lines: int = 50,
    token: str = "",
) -> None:
    """Live tail a systemd unit (or container, by name).

    Query params:
        token    the X-Debug-Token (browsers can't set custom WS headers)
        service  systemd unit name or container name; validated against
                 the same ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ whitelist as the
                 REST endpoints to prevent argv injection
        lines    initial backfill (default 50, max 5000)

    On connect: closes 1008 (policy violation) if token missing/invalid
    or service name malformed; otherwise opens the subprocess and streams
    its stdout as text frames until the client disconnects.
    """
    if not _CONTAINER_RE.match(service):
        await websocket.close(code=1008, reason="invalid service name")
        return

    token_path = Path(get_settings().debug_token_path)
    expected = ""
    if token_path.exists():
        expected = token_path.read_text().strip()
    if (
        not expected
        or not token
        or not secrets.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))
    ):
        await websocket.close(code=1008, reason="invalid or missing token")
        return

    lines = max(1, min(int(lines), 5000))

    await websocket.accept()

    # Two readers: journalctl (systemd unit) vs docker logs (container).
    # Heuristic: if service name matches a docker container, use docker logs.
    # Otherwise systemd journal.
    is_container = False
    try:
        proc_check = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "--type=container",
            service,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc_check.wait()
        is_container = proc_check.returncode == 0
    except Exception:
        pass

    if is_container:
        cmd = ["docker", "logs", "-f", "--tail", str(lines), service]
    else:
        cmd = ["journalctl", "-u", service, "-n", str(lines), "-f", "--no-pager"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        await websocket.send_text(f"[pit-debug] failed to spawn tail: {e}\n")
        await websocket.close(code=1011)
        return

    async def _pump(stream):
        if stream is None:
            return
        while True:
            chunk = await stream.readline()
            if not chunk:
                return
            try:
                await websocket.send_text(chunk.decode("utf-8", errors="replace"))
            except Exception:
                return

    pump_out = asyncio.create_task(_pump(proc.stdout))
    pump_err = asyncio.create_task(_pump(proc.stderr))

    try:
        while True:
            try:
                await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError, Exception):
                break
    finally:
        pump_out.cancel()
        pump_err.cancel()
        with contextlib.suppress(Exception):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except (TimeoutError, Exception):
            with contextlib.suppress(Exception):
                proc.kill()
        with contextlib.suppress(Exception):
            await websocket.close()

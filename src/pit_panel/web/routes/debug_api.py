"""Secret debug API — logs, certs, system info. Protected by token file.

All endpoints are READ-ONLY. Every successful and failed authentication
attempt is appended to an audit log that NEVER contains the token value.
"""

import asyncio
import contextlib
import logging
import os
import platform
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.sudo_ops import run_cmd
from pit_panel.web.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter()

_AUDIT_LOG_PATH = "/var/log/pit-panel/debug-audit.log"
_AUDIT_FALLBACK_PATH = "/tmp/pit-panel-debug-audit.log"

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
    if not secrets.compare_digest(x_debug_token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid debug token")
    return x_debug_token


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

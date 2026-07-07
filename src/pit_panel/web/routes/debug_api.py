"""Secret debug API — logs, certs, system info. Protected by token file."""

import asyncio
import logging
import os
import platform
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.sudo_ops import run_cmd

logger = logging.getLogger(__name__)
router = APIRouter()


def _verify_token(x_debug_token: str | None = Header(None)) -> str:
    import secrets

    if not x_debug_token:
        raise HTTPException(status_code=401, detail="Missing X-Debug-Token header")
    token_path = Path(get_settings().debug_token_path)
    if not token_path.exists():
        raise HTTPException(status_code=503, detail="Debug token not configured on this server")
    expected = token_path.read_text().strip()
    if not secrets.compare_digest(x_debug_token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid debug token")
    return x_debug_token


async def _run(cmd: list[str], timeout: int = 10, cwd: str | None = None) -> str:
    res = await run_cmd(cmd, timeout=timeout, cwd=cwd)
    if res.returncode == -1:
        if "timeout" in res.stderr.lower():
            return f"ERROR: Command timed out after {timeout} seconds"
        return f"ERROR: {res.stderr}"
    return (res.stdout + res.stderr).strip() or "(empty)"


@router.get("/api/debug/logs")  # type: ignore[untyped-decorator]
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
    return PlainTextResponse(await _run(args))


@router.get("/api/debug/certs")  # type: ignore[untyped-decorator]
async def debug_certs(
    request: Request,
    token: str = Depends(_verify_token),
) -> JSONResponse:
    caddy = CaddyManager(get_settings().caddy_admin_url)
    certs = await caddy.get_certificates()
    return JSONResponse(certs)


@router.get("/api/debug/system")  # type: ignore[untyped-decorator]
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
        }
    )

"""Diagnostics: git, network, system — copy-paste friendly for debug."""

import os
import platform
import shutil

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.sudo_ops import run_cmd
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()

INSTALL_DIR = "/opt/pit-panel"


async def _run(cmd: list[str], timeout: int = 10, cwd: str | None = None) -> str:
    res = await run_cmd(cmd, timeout=timeout, cwd=cwd)
    if res.returncode == -1:
        # If exception/timeout occurs, run_cmd returns returncode=-1 and error in stderr
        return f"ERROR: {res.stderr}"
    return (res.stdout + res.stderr).strip() or "(empty)"


def _file_checksum(path: str) -> str:
    import hashlib

    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception as e:
        return str(e)


@router.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    s = get_settings()

    import asyncio

    (
        git_version,
        git_remote,
        git_status,
        git_log,
        git_ls_remote,
        git_fetch_test,
        ping_github,
        curl_api,
        service_status,
        caddy_status,
        docker_status,
        journal_errors,
    ) = await asyncio.gather(
        _run(["git", "--version"]),
        _run(["git", "remote", "-v"], cwd=INSTALL_DIR),
        _run(["git", "status", "--short"], cwd=INSTALL_DIR),
        _run(["git", "log", "--oneline", "-5"], cwd=INSTALL_DIR),
        _run(
            [
                "git",
                "ls-remote",
                "https://github.com/pietrondo/pit-panel.git",
                "refs/heads/main",
            ],
            timeout=15,
        ),
        _run(["git", "fetch", "origin", "--dry-run"], timeout=15, cwd=INSTALL_DIR),
        _run(["ping", "-c", "1", "-W", "3", "github.com"]),
        _run(["curl", "-sI", "--max-time", "5", "https://api.github.com"]),
        _run(["systemctl", "status", "pit-panel.service", "--no-pager", "-l"]),
        _run(["systemctl", "is-active", "caddy"]),
        _run(["systemctl", "is-active", "docker"]),
        _run(["journalctl", "-u", "pit-panel.service", "-p", "3", "-n", "20", "--no-pager"]),
    )

    diag = {
        "python": platform.python_version(),
        "hostname": platform.node(),
        "cwd": os.getcwd(),
        "disk": shutil.disk_usage("/opt").free // (1024**2) if os.path.exists("/opt") else "?",
        "git_version": git_version,
        "git_remote": git_remote,
        "git_status": git_status,
        "git_log": git_log,
        "git_ls_remote": git_ls_remote,
        "git_fetch_test": git_fetch_test,
        "ping_github": ping_github,
        "curl_api": curl_api,
        "service_status": service_status,
        "service_file": _file_checksum("/etc/systemd/system/pit-panel.service"),
        "repo_service_file": _file_checksum(f"{INSTALL_DIR}/packaging/pit-panel.service"),
        "config_file": _file_checksum("/etc/pit-panel/config.toml"),
        "db_size": os.path.getsize(s.get_database_url().replace("sqlite+aiosqlite:///", ""))
        if os.path.exists(s.get_database_url().replace("sqlite+aiosqlite:///", ""))
        else "?",
        "caddy_status": caddy_status,
        "docker_status": docker_status,
        "journal_errors": journal_errors,
    }

    return render("debug.html", user=user, diag=diag)


@router.get("/debug/raw", response_class=PlainTextResponse)
async def debug_raw(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return PlainTextResponse("Unauthorized", status_code=401)

    lines = []
    lines.append("=== pit-panel debug report ===")
    lines.append(f"Python: {platform.python_version()}")
    lines.append(f"Hostname: {platform.node()}")
    lines.append("")
    lines.append("--- git ---")
    cmd_ls = [
        "git",
        "ls-remote",
        "https://github.com/pietrondo/pit-panel.git",
        "refs/heads/main",
    ]
    for label, cmd_args, wd in [
        ("version", ["git", "--version"], None),
        ("remote", ["git", "remote", "-v"], INSTALL_DIR),
        ("ls-remote", cmd_ls, None),
        ("log", ["git", "log", "--oneline", "-5"], INSTALL_DIR),
    ]:
        lines.append(f"[{label}]")
        lines.append(await _run(cmd_args, cwd=wd or None))
        lines.append("")
    lines.append("--- network ---")
    for label, cmd in [
        ("ping github", ["ping", "-c", "1", "-W", "3", "github.com"]),
        ("curl api", ["curl", "-sI", "--max-time", "5", "https://api.github.com"]),
    ]:
        lines.append(f"[{label}]")
        lines.append(await _run(cmd))
        lines.append("")
    lines.append("--- service ---")
    lines.append(await _run(["systemctl", "status", "pit-panel.service", "--no-pager", "-l"]))
    lines.append("")
    lines.append("--- errors ---")
    jctl = ["journalctl", "-u", "pit-panel.service", "-p", "3", "-n", "20", "--no-pager"]
    lines.append(await _run(jctl))

    return PlainTextResponse("\n".join(lines))

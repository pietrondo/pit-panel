"""Diagnostics: git, network, system — copy-paste friendly for debug."""

import os
import platform
import shutil
import subprocess

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token, validate_session
from pit_panel.web.render import render
from pit_panel.web.router import router

INSTALL_DIR = "/opt/pit-panel"


async def _get_admin(request: Request, db: AsyncSession) -> User | None:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    data = unsign_session_token, validate_session(settings, cookie)
    if not data:
        return None
    user = await validate_session(db, cookie, settings, data.get("uid", 0))
    if user and user.is_admin:
        return user
    return None


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip() or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"


def _file_checksum(path: str) -> str:
    import hashlib

    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception as e:
        return str(e)


@router.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    s = get_settings()

    diag = {
        "python": platform.python_version(),
        "hostname": platform.node(),
        "cwd": os.getcwd(),
        "disk": shutil.disk_usage("/opt").free // (1024**2) if os.path.exists("/opt") else "?",
        "git_version": _run(["git", "--version"]),
        "git_remote": _run(["git", "remote", "-v"], cwd=INSTALL_DIR),
        "git_status": _run(["git", "status", "--short"], cwd=INSTALL_DIR),
        "git_log": _run(["git", "log", "--oneline", "-5"], cwd=INSTALL_DIR),
        "git_ls_remote": _run(
            [
                "git", "ls-remote",
                "https://github.com/pietrondo/pit-panel.git",
                "refs/heads/main",
            ],
            timeout=15,
        ),
        "git_fetch_test": _run(
            ["git", "fetch", "origin", "--dry-run"], timeout=15, cwd=INSTALL_DIR
        ),
        "ping_github": _run(["ping", "-c", "1", "-W", "3", "github.com"]),
        "curl_api": _run(
            ["curl", "-sI", "--max-time", "5", "https://api.github.com"]
        ),
        "service_status": _run(["systemctl", "status", "pit-panel.service", "--no-pager", "-l"]),
        "service_file": _file_checksum("/etc/systemd/system/pit-panel.service"),
        "repo_service_file": _file_checksum(f"{INSTALL_DIR}/packaging/pit-panel.service"),
        "config_file": _file_checksum("/etc/pit-panel/config.toml"),
        "db_size": os.path.getsize(s.get_database_url().replace("sqlite+aiosqlite:///", ""))
        if os.path.exists(s.get_database_url().replace("sqlite+aiosqlite:///", ""))
        else "?",
        "caddy_status": _run(["systemctl", "is-active", "caddy"]),
        "docker_status": _run(["systemctl", "is-active", "docker"]),
        "journal_errors": _run(
            ["journalctl", "-u", "pit-panel.service", "-p", "3", "-n", "20", "--no-pager"]
        ),
    }

    return render("debug.html", user=user, diag=diag)


@router.get("/debug/raw", response_class=PlainTextResponse)
async def debug_raw(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return PlainTextResponse("Unauthorized", status_code=401)

    lines = []
    lines.append("=== pit-panel debug report ===")
    lines.append(f"Python: {platform.python_version()}")
    lines.append(f"Hostname: {platform.node()}")
    lines.append("")
    lines.append("--- git ---")
    cmd_ls = [
        "git", "ls-remote",
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
        lines.append(_run(cmd_args, cwd=wd or None))
        lines.append("")
    lines.append("--- network ---")
    for label, cmd in [
        ("ping github", ["ping", "-c", "1", "-W", "3", "github.com"]),
        ("curl api", ["curl", "-sI", "--max-time", "5", "https://api.github.com"]),
    ]:
        lines.append(f"[{label}]")
        lines.append(_run(cmd))
        lines.append("")
    lines.append("--- service ---")
    lines.append(_run(["systemctl", "status", "pit-panel.service", "--no-pager", "-l"]))
    lines.append("")
    lines.append("--- errors ---")
    jctl = ["journalctl", "-u", "pit-panel.service", "-p", "3", "-n", "20", "--no-pager"]
    lines.append(_run(jctl))

    return PlainTextResponse("\n".join(lines))

"""Application log viewer."""

import subprocess

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token
from pit_panel.web.render import render
from pit_panel.web.router import router

APP_LOG = "/var/log/pit-panel/app.log"
DOCKER_LOG_DIR = "/var/log/pit-panel/docker"
SYSLOG_CMD = ["journalctl", "-u", "pit-panel.service", "-n", "200", "--no-pager"]


async def _get_admin(request: Request, db: AsyncSession) -> User | None:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    data = unsign_session_token(settings, cookie)
    if not data:
        return None
    result = await db.execute(select(User).where(User.id == data.get("uid")))
    user = result.scalar_one_or_none()
    if user and user.is_admin:
        return user
    return None


def _read_log(path: str, tail: int = 500) -> str:
    try:
        with open(path) as f:
            lines = f.readlines()
            return "".join(lines[-tail:])
    except (FileNotFoundError, PermissionError):
        return "[log file not found or inaccessible]"


def _read_journal(n: int = 200) -> str:
    # Try direct access first (pit-panel in systemd-journal group)
    try:
        result = subprocess.run(
            ["journalctl", "-u", "pit-panel.service", "-n", str(n), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            return result.stdout
    except Exception:
        pass
    # Fallback: try with sudo
    try:
        result = subprocess.run(
            ["sudo", "-n", "journalctl", "-u", "pit-panel.service", "-n", str(n), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            return result.stdout
    except Exception:
        pass
    return "[journal unavailable — pit-panel user needs systemd-journal group]"


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    app_log = _read_log(APP_LOG)
    journal = _read_journal()

    return render(
        "logs.html",
        user=user,
        app_log=app_log,
        journal=journal,
    )


@router.get("/logs/journal", response_class=HTMLResponse)
async def journal_partial(request: Request):
    journal = _read_journal()
    return HTMLResponse(
        f'<pre class="text-xs font-mono text-green-400 whitespace-pre-wrap">{journal}</pre>'
    )


@router.get("/logs/applog", response_class=HTMLResponse)
async def applog_partial(request: Request):
    app_log = _read_log(APP_LOG)
    return HTMLResponse(
        f'<pre class="text-xs font-mono text-green-400 whitespace-pre-wrap">{app_log}</pre>'
    )

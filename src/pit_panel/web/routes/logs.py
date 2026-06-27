"""Application log viewer."""

import asyncio
import html
import os
import subprocess

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()

APP_LOG = "/var/log/pit-panel/app.log"
DOCKER_LOG_DIR = "/var/log/pit-panel/docker"
SYSLOG_CMD = ["journalctl", "-u", "pit-panel.service", "-n", "200", "--no-pager"]


def _read_log_sync(path: str, tail: int) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0:
                return ""

            buffer_size = 8192
            blocks = []
            lines_found = 0
            position = file_size

            while position > 0 and lines_found <= tail:
                read_size = min(buffer_size, position)
                position -= read_size
                f.seek(position)
                block = f.read(read_size)
                lines_found += block.count(b"\n")
                blocks.append(block)

            data = b"".join(reversed(blocks))
            lines = data.splitlines(keepends=True)
            return b"".join(lines[-tail:]).decode("utf-8", errors="replace")
    except (FileNotFoundError, PermissionError):
        return "[log file not found or inaccessible]"


async def _read_log(path: str, tail: int = 500) -> str:
    return await asyncio.to_thread(_read_log_sync, path, tail)


def _read_journal_sync(n: int) -> str:
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


async def _read_journal(n: int = 200) -> str:
    return await asyncio.to_thread(_read_journal_sync, n)


@router.get("/logs", response_class=HTMLResponse, response_model=None)
async def logs_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    app_log = await _read_log(APP_LOG)
    journal = await _read_journal()

    response = render(
        "logs.html",
        user=user,
        app_log=app_log,
        journal=journal,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@router.get("/logs/journal", response_class=HTMLResponse)
async def journal_partial(request: Request) -> HTMLResponse:
    journal = await _read_journal()
    escaped = html.escape(journal)
    pre = (
        '<pre id="journal-box" '
        'class="text-xs font-mono text-green-400 leading-relaxed whitespace-pre-wrap">'
    )
    return HTMLResponse(f"{pre}{escaped}</pre>")


@router.get("/logs/applog", response_class=HTMLResponse)
async def applog_partial(request: Request) -> HTMLResponse:
    app_log = await _read_log(APP_LOG)
    escaped = html.escape(app_log)
    pre = (
        '<pre id="applog-box" '
        'class="text-xs font-mono text-green-400 leading-relaxed whitespace-pre-wrap">'
    )
    return HTMLResponse(f"{pre}{escaped}</pre>")

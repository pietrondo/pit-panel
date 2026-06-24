"""System: upgrade check and trigger with self-restart."""

import contextlib
import datetime as dt
import os
import subprocess
import sys

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import UpdateHistory, User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token
from pit_panel.web.render import render
from pit_panel.web.router import router

INSTALL_DIR = "/opt/pit-panel"


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


def _get_git_info():
    current = "unknown"
    remote = "unknown"
    with contextlib.suppress(Exception):
        current = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=INSTALL_DIR,
        ).stdout.strip()
    with contextlib.suppress(Exception):
        result = subprocess.run(
            [
                "git", "ls-remote",
                "https://github.com/pietrondo/pit-panel.git",
                "refs/heads/main",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            remote = result.stdout.split()[0][:7]
    if remote == "unknown":
        with contextlib.suppress(Exception):
            import json
            import ssl
            import urllib.request

            url = "https://api.github.com/repos/pietrondo/pit-panel/commits/main"
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "pit-panel",
            })
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read())
                api_sha = data.get("sha", "")[:7]
                if api_sha:
                    remote = api_sha
    return current, remote


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    current, remote = _get_git_info()
    update_available = current != remote and remote != "unknown"

    result = await db.execute(
        select(UpdateHistory).order_by(UpdateHistory.started_at.desc()).limit(10)
    )
    history = result.scalars().all()

    return render(
        "system.html",
        user=user,
        current_version=current,
        remote_version=remote,
        update_available=update_available,
        update_history=history,
        upgrade_result=None,
    )


@router.post("/system/upgrade", response_class=HTMLResponse)
async def system_upgrade(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # Run git operations directly in-process
    result_msg = ""
    try:
        subprocess.run(
            ["git", "fetch", "origin", "--prune"],
            capture_output=True, timeout=60, cwd=INSTALL_DIR,
            check=True,
        )
        subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            capture_output=True, timeout=30, cwd=INSTALL_DIR,
            check=True,
        )
        subprocess.run(
            ["uv", "sync"], capture_output=True, timeout=120, cwd=INSTALL_DIR, check=True
        )
        # Try to copy service file (may fail if no sudo)
        with contextlib.suppress(Exception):
            subprocess.run(
                ["cp", f"{INSTALL_DIR}/packaging/pit-panel.service",
                 "/etc/systemd/system/pit-panel.service"],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["systemctl", "daemon-reload"], capture_output=True, timeout=10,
            )
        result_msg = "Upgrade complete. Restarting..."
    except subprocess.CalledProcessError as e:
        result_msg = f"Upgrade failed: {e.stderr[:200] if e.stderr else e}"

    # Log to update history
    try:
        current, _ = _get_git_info()
        entry = UpdateHistory(
            version_from=current,
            version_to="latest",
            status="completed" if "complete" in result_msg else "failed",
            started_at=dt.datetime.now(dt.UTC),
            completed_at=dt.datetime.now(dt.UTC),
        )
        db.add(entry)
        await db.commit()
    except Exception:
        pass

    # Self-restart: replace current process with new code
    if "complete" in result_msg:
        os.execv(sys.executable, [sys.executable, "-c", "from pit_panel.main import main; main()"])

    current, remote = _get_git_info()
    return render(
        "system.html",
        user=user,
        current_version=current,
        remote_version=remote,
        update_available=False,
        update_history=[],
        upgrade_result=result_msg,
    )

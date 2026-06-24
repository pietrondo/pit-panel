"""System: upgrade check and trigger."""

import contextlib
import subprocess

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
        subprocess.run(
            ["git", "fetch", "origin"], capture_output=True, timeout=30,
            cwd=INSTALL_DIR,
        )
        remote = subprocess.run(
            ["git", "rev-parse", "--short", "origin/main"],
            capture_output=True, text=True, timeout=10,
            cwd=INSTALL_DIR,
        ).stdout.strip()
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

    # Run upgrade via sudo (pit-panel has NOPASSWD sudoers for this script).
    # Falls back to direct execution if sudo not available (first install).
    try:
        subprocess.Popen(
            ["sudo", "-n", "bash", f"{INSTALL_DIR}/scripts/upgrade.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=INSTALL_DIR,
        )
    except Exception:
        with contextlib.suppress(Exception):
            subprocess.Popen(
                ["bash", f"{INSTALL_DIR}/scripts/upgrade.sh"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=INSTALL_DIR,
            )

    current, remote = _get_git_info()

    result = await db.execute(
        select(UpdateHistory).order_by(UpdateHistory.started_at.desc()).limit(10)
    )
    history = result.scalars().all()

    return render(
        "system.html",
        user=user,
        current_version=current,
        remote_version=remote,
        update_available=False,
        update_history=history,
        upgrade_result="Upgrade started in background. Page will reload shortly.",
    )

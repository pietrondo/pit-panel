"""System: upgrade check and trigger via sudo."""

import asyncio
import contextlib
import datetime as dt
import subprocess

import httpx
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


def _sudo(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a privileged command via sudo -n (non-interactive, no password prompt).

    Required because pit-panel runs under systemd ProtectSystem=strict
    and cannot write to /opt/pit-panel/.git/ or /etc/systemd/system/.
    """
    return subprocess.run(
        ["sudo", "-n", *cmd],
        capture_output=True, text=True, timeout=timeout,
    )


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


async def _get_git_info():
    current = "unknown"
    remote = "unknown"
    with contextlib.suppress(Exception):
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--short", "HEAD",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=INSTALL_DIR,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        current = stdout.decode().strip()
    with contextlib.suppress(Exception):
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote",
            "https://github.com/pietrondo/pit-panel.git",
            "refs/heads/main",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0 and stdout.strip():
            remote = stdout.decode().split()[0][:7]
    if remote == "unknown":
        with contextlib.suppress(Exception):
            url = "https://api.github.com/repos/pietrondo/pit-panel/commits/main"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "pit-panel",
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    api_sha = data.get("sha", "")[:7]
                    if api_sha:
                        remote = api_sha
    return current, remote


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    current, remote = await _get_git_info()
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

    # All privileged operations run via sudo -n.
    # The pit-panel service runs under systemd ProtectSystem=strict
    # and cannot write to /opt/pit-panel/.git/ or /etc/systemd/system/.
    steps = [
        (["git", "-C", INSTALL_DIR, "fetch", "origin", "--prune"], 60),
        (["git", "-C", INSTALL_DIR, "reset", "--hard", "origin/main"], 30),
        (["uv", "--directory", INSTALL_DIR, "sync"], 180),
        (["cp", f"{INSTALL_DIR}/packaging/pit-panel.service",
          "/etc/systemd/system/pit-panel.service"], 10),
        (["systemctl", "daemon-reload"], 10),
        (["systemctl", "restart", "pit-panel.service"], 30),
    ]

    log_lines: list[str] = []
    ok = True
    for cmd, timeout in steps:
        result = _sudo(cmd, timeout=timeout)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()[:200]
            log_lines.append(f"FAIL {' '.join(cmd)}: {err}")
            ok = False
            break
        log_lines.append(f"OK   {' '.join(cmd)}")

    result_msg = "\n".join(log_lines) if log_lines else "no steps ran"

    try:
        current, _ = await _get_git_info()
        entry = UpdateHistory(
            version_from=current,
            version_to="latest",
            status="completed" if ok else "failed",
            started_at=dt.datetime.now(dt.UTC),
            completed_at=dt.datetime.now(dt.UTC),
        )
        db.add(entry)
        await db.commit()
    except Exception:
        pass

    current, remote = await _get_git_info()
    return render(
        "system.html",
        user=user,
        current_version=current,
        remote_version=remote,
        update_available=False,
        update_history=[],
        upgrade_result=result_msg,
    )

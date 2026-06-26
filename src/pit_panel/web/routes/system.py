"""System: upgrade check and trigger via sudo."""

import datetime as dt
import subprocess

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.db.models import UpdateHistory
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render
from pit_panel.web.router import router

INSTALL_DIR = "/opt/pit-panel"


def _sudo(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a privileged command via sudo -n (non-interactive, no password prompt).

    Used for systemctl and cp operations that require root.
    """
    return subprocess.run(
        ["sudo", "-n", *cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a command as the pit-panel user (no sudo)."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


async def _get_git_info() -> tuple[str, str]:
    import asyncio

    import httpx

    current = "unknown"
    remote = "unknown"

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--short",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=INSTALL_DIR,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            current = stdout.decode().strip()
    except Exception:
        pass

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            "https://github.com/pietrondo/pit-panel.git",
            "refs/heads/main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0 and stdout.strip():
            remote = stdout.decode().split()[0][:7]
    except Exception:
        pass

    if remote == "unknown":
        try:
            url = "https://api.github.com/repos/pietrondo/pit-panel/commits/main"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "pit-panel",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    api_sha = data.get("sha", "")[:7]
                    if api_sha:
                        remote = api_sha
        except Exception:
            pass

    return current, remote


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
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
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # git and uv run directly (repo is owned by pit-panel, in ReadWritePaths).
    # cp and systemctl require sudo.
    steps = [
        (["git", "-C", INSTALL_DIR, "fetch", "origin", "--prune"], 60, False),
        (["git", "-C", INSTALL_DIR, "reset", "--hard", "origin/main"], 30, False),
        (["/usr/local/bin/uv", "--directory", INSTALL_DIR, "sync"], 180, False),
        (
            [
                "cp",
                f"{INSTALL_DIR}/packaging/pit-panel.service",
                "/etc/systemd/system/",
            ],
            10,
            True,
        ),
        (["systemctl", "daemon-reload"], 10, True),
    ]

    log_lines: list[str] = []
    ok = True
    for cmd, timeout, use_sudo in steps:
        result = _sudo(cmd, timeout=timeout) if use_sudo else _run(cmd, timeout=timeout)
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

    if ok:
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "restart", "--no-block", "pit-panel.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result_msg += "\nOK   systemctl restart --no-block pit-panel.service (queued)"

    return render(
        "system.html",
        user=user,
        current_version=current,
        remote_version=remote,
        update_available=False,
        update_history=[],
        upgrade_result=result_msg,
    )

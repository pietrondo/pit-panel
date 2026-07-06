"""System: upgrade check and trigger via sudo."""

import datetime as dt
import os
import shutil
import subprocess
import sys

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.db.models import UpdateHistory
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()

INSTALL_DIR = "/opt/pit-panel"


async def _sudo(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a privileged command via sudo -n (non-interactive, no password prompt).

    Used for systemctl and cp operations that require root.
    """
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "sudo", "-n", *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return subprocess.CompletedProcess(
            args=["sudo", "-n", *cmd], returncode=-1, stdout="", stderr="Timeout"
        )

    return subprocess.CompletedProcess(
        args=["sudo", "-n", *cmd],
        returncode=proc.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


async def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a command as the pit-panel user (no sudo)."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return subprocess.CompletedProcess(args=cmd, returncode=-1, stdout="", stderr="Timeout")

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


async def _get_current_sha() -> str:
    """Get the current git commit SHA of the installation directory."""
    res = await _run(["git", "-C", INSTALL_DIR, "rev-parse", "HEAD"])
    if res.returncode != 0:
        raise RuntimeError(f"Failed to retrieve current git SHA: {res.stderr or res.stdout}")
    return res.stdout.strip()


def _resolve_uv_bin() -> str:
    """Resolve the path of the uv executable dynamically."""
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path

    fallbacks = [
        "/usr/local/bin/uv",
        "/usr/bin/uv",
        "/opt/pit-panel/.venv/bin/uv",
        "/root/.cargo/bin/uv",
    ]
    for fb in fallbacks:
        if os.path.exists(fb):
            return fb

    raise FileNotFoundError("Could not resolve uv binary path")


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

    log_lines: list[str] = []
    ok = True

    try:
        original_sha = await _get_current_sha()
    except Exception as e:
        original_sha = "unknown"
        log_lines.append(f"FAIL git SHA check: {e}")
        ok = False

    if ok:
        try:
            uv_bin = _resolve_uv_bin()
        except Exception as e:
            log_lines.append(f"FAIL uv path check: {e}")
            ok = False

    if ok:
        python_bin = sys.executable
        steps = [
            (["git", "-C", INSTALL_DIR, "fetch", "origin", "--prune"], 60, False),
            (["git", "-C", INSTALL_DIR, "reset", "--hard", "origin/main"], 30, False),
            ([uv_bin, "--directory", INSTALL_DIR, "sync"], 180, False),
            ([python_bin, "-m", "compileall", "-q", f"{INSTALL_DIR}/src"], 30, False),
            (
                [
                    "/bin/cp",
                    f"{INSTALL_DIR}/packaging/pit-panel.service",
                    "/etc/systemd/system/",
                ],
                10,
                True,
            ),
            (["/usr/bin/systemctl", "daemon-reload"], 10, True),
        ]

        for cmd, timeout, use_sudo in steps:
            result = (
                await _sudo(cmd, timeout=timeout) if use_sudo else await _run(cmd, timeout=timeout)
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip()[:200]
                log_lines.append(f"FAIL {' '.join(cmd)}: {err}")
                ok = False
                break
            log_lines.append(f"OK   {' '.join(cmd)}")

        if not ok:
            log_lines.append(f"[ROLLBACK] Restoring codebase to SHA {original_sha[:7]}...")
            rollback_steps = [
                (["git", "-C", INSTALL_DIR, "reset", "--hard", original_sha], 30, False),
                ([uv_bin, "--directory", INSTALL_DIR, "sync"], 180, False),
                (["/usr/bin/systemctl", "daemon-reload"], 10, True),
            ]
            for rb_cmd, rb_timeout, rb_use_sudo in rollback_steps:
                if rb_use_sudo:
                    rb_result = await _sudo(rb_cmd, timeout=rb_timeout)
                else:
                    rb_result = await _run(rb_cmd, timeout=rb_timeout)

                if rb_result.returncode != 0:
                    rb_err = (rb_result.stderr or rb_result.stdout or "").strip()[:200]
                    log_lines.append(f"[ROLLBACK] FAIL {' '.join(rb_cmd)}: {rb_err}")
                else:
                    log_lines.append(f"[ROLLBACK] OK   {' '.join(rb_cmd)}")

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
            ["sudo", "-n", "/usr/bin/systemctl", "restart", "--no-block", "pit-panel.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result_msg += "\nOK   /usr/bin/systemctl restart --no-block pit-panel.service (queued)"

    return render(
        "system.html",
        user=user,
        current_version=current,
        remote_version=remote,
        update_available=False,
        update_history=[],
        upgrade_result=result_msg,
    )

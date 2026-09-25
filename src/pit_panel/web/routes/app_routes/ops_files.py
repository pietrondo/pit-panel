"""App operations: containers, backup, logs, env, status, files."""

import asyncio
import contextlib
import datetime
import logging
import os
import shutil
import tarfile
from pathlib import Path

from fastapi import Depends, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.docker_ops import DockerManager
from pit_panel.db.models import AuditLog, Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

from .router import router

logger = logging.getLogger(__name__)


def _safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    """Extract regular files/directories without permitting archive traversal."""
    root = destination.resolve()
    members = archive.getmembers()
    for member in members:
        target = (root / member.name).resolve()
        if not target.is_relative_to(root) or member.issym() or member.islnk():
            raise ValueError("Unsafe backup archive member")
        if not (member.isdir() or member.isreg()):
            raise ValueError("Unsupported backup archive member")

    for member in members:
        target = root / member.name
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("Unreadable backup archive member")
        with source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


@router.get("/apps/{sd_id}/containers", response_class=HTMLResponse)
async def app_containers_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    containers = []
    with contextlib.suppress(Exception):
        containers = await docker_mgr.compose_ps(sd.subdomain)

    return render("tabs/_containers.html", request=request, sd=sd, containers=containers)


@router.get("/apps/{sd_id}/backup", response_class=HTMLResponse)
async def app_backup_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    backups_dir2 = Path(get_settings().data_dir) / "backups" / sd.subdomain
    backups = []
    if backups_dir2.exists():
        for f in sorted(backups_dir2.iterdir(), reverse=True)[:20]:
            if f.suffix == ".tar.gz":
                sz = f.stat().st_size
                sz_str = f"{sz / 1024 / 1024:.1f} MB" if sz > 1048576 else f"{sz / 1024:.0f} KB"
                dt = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                backups.append({"name": f.stem.replace(".tar", ""), "size": sz_str, "date": dt})
    import json as _json

    return render(
        "tabs/_backup.html",
        request=request,
        sd=sd,
        backups=backups,
        backups_json=_json.dumps(backups),
    )


@router.post("/apps/{sd_id}/backup/run", response_class=HTMLResponse)
async def app_backup_run(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("<p class='text-red-500'>Unauthorized</p>", status_code=401)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<p class='text-red-500'>App not found</p>", status_code=404)

    settings = get_settings()
    from pit_panel.core.backup import perform_app_backup

    backup_result = await perform_app_backup(
        sd=sd,
        db=db,
        settings=settings,
        user_id=user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if backup_result.get("success"):
        name = backup_result["name"]
        size_str = backup_result["size_str"]
        html_ok = (
            '<div class="px-6 py-3 bg-green-50 dark:bg-green-900/20'
            ' border-b border-green-200 dark:border-green-800">'
            f'<p class="text-sm text-green-700 dark:text-green-400">'
            f"Backup created: {name} ({size_str})</p></div>"
        )
        return HTMLResponse(html_ok)
    else:
        err = backup_result.get("error", "Unknown error")
        html_err = (
            '<div class="px-6 py-3 bg-red-50 dark:bg-red-900/20'
            ' border-b border-red-200 dark:border-red-800">'
            f'<p class="text-sm text-red-700 dark:text-red-400">'
            f"Backup failed: {err}</p></div>"
        )
        return HTMLResponse(html_err)


@router.post("/apps/{sd_id}/backup/restore", response_class=HTMLResponse)
async def app_backup_restore(
    request: Request, sd_id: int, name: str = Form(...), db: AsyncSession = Depends(get_db)
):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("<p class='text-red-500'>Unauthorized</p>", status_code=401)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<p class='text-red-500'>App not found</p>", status_code=404)

    settings = get_settings()
    backup_path = Path(settings.data_dir) / "backups" / sd.subdomain / f"{name}.tar.gz"
    if not backup_path.exists():
        return HTMLResponse("<p class='text-red-500'>Backup not found</p>", status_code=404)

    docker_mgr = DockerManager(settings.apps_dir)

    try:
        await docker_mgr.run_compose_command(sd.subdomain, ["down"])
        with tarfile.open(backup_path, "r:gz") as tar:
            _safe_extract_tar(tar, Path(settings.apps_dir))
        await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])

        db.add(
            AuditLog(
                user_id=user.id,
                action="app_backup_restore",
                target_type="subdomain",
                target_id=sd.id,
                details={"backup": name},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()

        return HTMLResponse(
            '<div class="px-6 py-3 bg-green-50 dark:bg-green-900/20'
            ' border-b border-green-200 dark:border-green-800">'
            f'<p class="text-sm text-green-700 dark:text-green-400">'
            f"Restored: {name}</p></div>"
        )
    except Exception as e:
        logger.error(f"Restore failed for {sd.subdomain}: {e}")
        return HTMLResponse(
            '<div class="px-6 py-3 bg-red-50 dark:bg-red-900/20'
            ' border-b border-red-200 dark:border-red-800">'
            f'<p class="text-sm text-red-600">Restore failed: {e}</p></div>'
        )


@router.get("/apps/{sd_id}/logs", response_class=HTMLResponse)
async def app_logs_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    logs = ""
    try:
        logs = await docker_mgr.compose_logs(sd.subdomain, tail=50)
    except Exception:
        logs = "Error fetching logs"

    return render("tabs/_logs.html", request=request, sd=sd, logs=logs)


async def _stream_websocket(
    websocket: WebSocket, proc: asyncio.subprocess.Process, forward_stdin: bool
) -> None:
    """Pump subprocess stdout to the socket; optionally forward input to stdin."""

    async def reader() -> None:
        try:
            while True:
                data = await proc.stdout.read(4096)
                if not data:
                    break
                await websocket.send_text(data.decode(errors="replace"))
        except Exception:
            pass
        finally:
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                await websocket.close()

    async def writer() -> None:
        try:
            while True:
                data = await websocket.receive_text()
                if forward_stdin and proc.stdin and not proc.stdin.is_closing():
                    proc.stdin.write(data.encode())
                    await proc.stdin.drain()
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            with contextlib.suppress(Exception):
                proc.kill()

    await asyncio.gather(reader(), writer())


@router.websocket("/apps/{sd_id}/logs/ws")
async def app_logs_ws(websocket: WebSocket, sd_id: int, db: AsyncSession = Depends(get_db)):
    await websocket.accept()

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        await websocket.send_text("ERROR: App not found")
        await websocket.close()
        return

    settings = get_settings()
    compose_path = Path(settings.apps_dir) / sd.subdomain / "docker-compose.yml"
    cwd = str(Path(settings.apps_dir) / sd.subdomain)

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            str(compose_path),
            "logs",
            "--tail=50",
            "--follow",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
    except OSError as e:
        await websocket.send_text(f"ERROR: {e}")
        await websocket.close()
        return

    await _stream_websocket(websocket, proc, forward_stdin=False)


@router.get("/apps/{sd_id}/env", response_class=HTMLResponse)
async def app_env_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    env_path = os.path.join(settings.apps_dir, sd.subdomain, ".env")
    env_content = ""
    if os.path.exists(env_path):
        try:

            def _read_env() -> str:
                with open(env_path) as f:
                    return f.read()

            env_content = await asyncio.to_thread(_read_env)
        except Exception as e:
            logger.error(f"Failed to read .env file at {env_path}: {e}")
            env_content = "# Error reading .env file"
    else:
        env_content = "# No .env file found"

    return render(
        "tabs/_env.html", request=request, sd=sd, env_content=env_content, error=None, success=None
    )


@router.post("/apps/{sd_id}/env", response_class=HTMLResponse)
async def app_env_post(
    request: Request, sd_id: int, env_content: str = Form(...), db: AsyncSession = Depends(get_db)
):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    env_path = os.path.join(settings.apps_dir, sd.subdomain, ".env")

    if any(c in env_content for c in ['"', "'"]):
        return HTMLResponse("Quotes are not allowed to prevent quote evasion.", status_code=400)
    if any(c in env_content for c in ["$", "`", "\\", ";", "|", "&"]) or "$(" in env_content:
        return HTMLResponse("Shell operators are not allowed.", status_code=400)

    error = None
    success = None
    try:
        safe_content = env_content.replace("\r", "")
        await asyncio.to_thread(Path(env_path).write_text, safe_content)
        success = (
            "Environment variables updated successfully. "
            "You may need to restart the app for changes to take effect."
        )

        db.add(
            AuditLog(
                user_id=user.id,
                action="app_env_update",
                target_type="subdomain",
                target_id=sd.id,
                details={"subdomain": sd.subdomain},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to save .env file for {sd.subdomain}: {e}")
        error = f"Error saving .env file: {e}"

    return render(
        "tabs/_env.html",
        request=request,
        sd=sd,
        env_content=env_content,
        error=error,
        success=success,
    )


@router.get("/apps/{sd_id}/status", response_class=HTMLResponse)
async def app_status_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    total_count = 0
    running_count = 0

    if sd.app_type:
        try:
            containers = await docker_mgr.compose_ps(sd.subdomain)
            total_count = len(containers)
            for c in containers:
                status = c.get("Status", "") or c.get("State", "") or ""
                if "up" in status.lower():
                    running_count += 1
        except Exception as e:
            logger.error(f"Failed to fetch container status for {sd.subdomain}: {e}")

    return render(
        "partials/_app_status.html",
        request=request,
        running_count=running_count,
        total_count=total_count,
    )


@router.get("/apps/{sd_id}/files", response_class=HTMLResponse)
async def app_files_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    app_dir = Path(settings.apps_dir) / sd.subdomain
    rel = request.query_params.get("path", "").lstrip("/")
    current = app_dir / rel if rel else app_dir

    # Security: prevent escaping the app dir
    try:
        current = current.resolve()
        current.relative_to(app_dir.resolve())
    except ValueError:
        return HTMLResponse("<div class='text-red-500'>Invalid path</div>", status_code=400)

    if current.is_file():
        try:
            content = current.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            content = "(binary file — preview not available)"
        return render(
            "partials/_file_content.html",
            request=request,
            sd=sd,
            path=str(rel),
            content=content,
        )

    entries = []
    try:
        for e in sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            entries.append(
                {
                    "name": e.name,
                    "is_dir": e.is_dir(),
                    "size": e.stat().st_size if e.is_file() else 0,
                }
            )
    except OSError:
        return HTMLResponse("<div class='text-red-500'>Cannot read directory</div>")

    parent = str(Path(rel).parent) if rel else ""
    return render(
        "partials/_files.html",
        request=request,
        sd=sd,
        entries=entries,
        current=rel,
        parent=parent,
        app_dir_name=app_dir.name,
    )


@router.post("/apps/{sd_id}/files/save", response_class=HTMLResponse)
async def app_files_save(
    request: Request,
    sd_id: int,
    path: str = Form(...),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>", status_code=404)

    settings = get_settings()
    app_dir = Path(settings.apps_dir) / sd.subdomain
    target = (app_dir / path.lstrip("/")).resolve()
    try:
        target.relative_to(app_dir.resolve())
    except ValueError:
        return HTMLResponse("<div class='text-red-500'>Invalid path</div>", status_code=400)

    if not target.exists():
        return HTMLResponse("<div class='text-red-500'>File not found</div>", status_code=404)

    try:
        safe_content = content.replace("\r", "")
        target.write_text(safe_content, encoding="utf-8")
        return HTMLResponse("<span class='text-green-600 text-sm'>Saved ✓</span>")
    except Exception as e:
        logger.error(f"Failed to save {target}: {e}")
        return HTMLResponse(f"<span class='text-red-500 text-sm'>Error: {e}</span>")

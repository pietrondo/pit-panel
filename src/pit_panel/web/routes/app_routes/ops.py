"""App operations: restart, stop, delete, status, containers, env, backup, logs."""

import contextlib
import logging
import os
import shutil
from pathlib import Path

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.app_manager import AppManager
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.docker_ops import DockerManager
from pit_panel.db.models import AppDeployment, AuditLog, Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

from .router import router

logger = logging.getLogger(__name__)


@router.post("/apps/{sd_id}/restart", response_class=HTMLResponse)
async def app_restart(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.run_compose_command(sd.subdomain, ["restart"])
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/apps/{sd_id}"
    return response


@router.post("/apps/{sd_id}/update", response_class=HTMLResponse)
async def app_update(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        r = await docker_mgr.run_compose_command(sd.subdomain, ["pull"])
        if r.get("success"):
            await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
        db.add(
            AuditLog(
                user_id=user.id,
                action="app_update",
                target_type="subdomain",
                target_id=sd.id,
                details={"subdomain": sd.subdomain, "pull_ok": r.get("success")},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/apps/{sd_id}"
    return response


@router.post("/apps/{sd_id}/stop", response_class=HTMLResponse)
async def app_stop(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.run_compose_command(sd.subdomain, ["down"])
        db.add(
            AuditLog(
                user_id=user.id,
                action="app_stop",
                target_type="subdomain",
                target_id=sd.id,
                details={"subdomain": sd.subdomain},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
    return RedirectResponse("/apps", status_code=302)


@router.post("/apps/{sd_id}/clone", response_class=HTMLResponse)
async def app_clone(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd or not sd.app_type:
        return RedirectResponse("/apps", status_code=302)

    settings = get_settings()
    base = sd.subdomain
    suffix = 1
    while (Path(settings.apps_dir) / f"{base}-clone{suffix}").exists():
        suffix += 1
    clone_name = f"{base}-clone{suffix}"

    # Copy app directory
    shutil.copytree(
        Path(settings.apps_dir) / base,
        Path(settings.apps_dir) / clone_name,
    )

    # Create DB record
    clone_sd = Subdomain(
        subdomain=clone_name,
        base_domain=sd.base_domain or settings.base_domain,
        owner_user_id=user.id,
        app_type=sd.app_type,
    )
    db.add(clone_sd)
    db.add(
        AuditLog(
            user_id=user.id,
            action="app_clone",
            target_type="subdomain",
            target_id=clone_sd.id,
            details={"source": base, "clone": clone_name},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    return RedirectResponse(f"/apps/{clone_sd.id}", status_code=302)


@router.post("/apps/{sd_id}/delete", response_class=HTMLResponse)
async def app_delete(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()

        # 1. Stop containers and remove volumes
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.run_compose_command(sd.subdomain, ["down", "-v"])

        # 2. Delete Caddy route
        if settings.base_domain and sd.app_type:
            try:
                caddy = CaddyManager(settings.caddy_admin_url)
                if sd.is_main_domain:
                    await caddy.remove_main_domain(settings.base_domain)
                else:
                    await caddy.remove_subdomain(sd.subdomain, settings.base_domain)
            except Exception as e:
                logger.warning(f"Failed to remove Caddy route for {sd.subdomain}: {e}")

        # 3. Delete app files
        mgr = AppManager(settings.apps_dir)
        mgr.delete_app(sd.subdomain)

        # 4. Reset subdomain app_type
        old_app_type = sd.app_type
        sd.app_type = None

        # 5. Delete AppDeployment DB records
        await db.execute(
            AppDeployment.__table__.delete().where(AppDeployment.subdomain_id == sd.id)
        )

        db.add(
            AuditLog(
                user_id=user.id,
                action="app_delete",
                target_type="subdomain",
                target_id=sd.id,
                details={"subdomain": sd.subdomain, "app_type": old_app_type},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
    return RedirectResponse("/apps", status_code=302)


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

    return render("tabs/_backup.html", request=request, sd=sd)


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
        return "<div class='text-red-500'>App not found</div>"

    settings = get_settings()
    env_path = os.path.join(settings.apps_dir, sd.subdomain, ".env")
    env_content = ""
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                env_content = f.read()
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
        return "<div class='text-red-500'>App not found</div>"

    settings = get_settings()
    env_path = os.path.join(settings.apps_dir, sd.subdomain, ".env")

    if any(c in env_content for c in ['"', "'"]):
        return HTMLResponse("Quotes are not allowed to prevent quote evasion.", status_code=400)

    error = None
    success = None
    try:
        with open(env_path, "w") as f:
            safe_content = env_content.replace("\r", "")
            f.write(safe_content)
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

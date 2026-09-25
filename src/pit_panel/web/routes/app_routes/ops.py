"""App actions: restart, update, delete, clone, stop, renew SSL."""

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import Depends, Request
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
        app_dir = Path(settings.apps_dir) / sd.subdomain / "app"

        is_repo = (app_dir / ".git").is_dir()
        if is_repo:
            pull = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(app_dir),
                "pull",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, pull_stderr = await asyncio.wait_for(pull.communicate(), timeout=120)
            pull_ok = pull.returncode == 0
            r = {"success": pull_ok, "stderr": pull_stderr.decode(errors="replace")}
            if pull_ok:
                await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
        else:
            r = await docker_mgr.run_compose_command(sd.subdomain, ["pull"])
            if r.get("success"):
                await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])

        db.add(
            AuditLog(
                user_id=user.id,
                action="app_update",
                target_type="subdomain",
                target_id=sd.id,
                details={
                    "subdomain": sd.subdomain,
                    "source": "git" if is_repo else "docker",
                    "pull_ok": r.get("success"),
                },
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
        if r.get("success"):
            from pit_panel.core.notifier import notify_app_update

            await notify_app_update(sd.subdomain)
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/apps/{sd_id}"
    return response


@router.post("/apps/{sd_id}/renew-ssl", response_class=HTMLResponse)
async def app_renew_ssl(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse(
            "<span class='text-red-500 text-xs'>App not found</span>", status_code=404
        )

    settings = get_settings()
    base_domain = sd.base_domain or settings.base_domain
    fqdn = f"{sd.subdomain}.{base_domain}"
    caddy = CaddyManager(settings.caddy_admin_url)

    # Step 1: ensure Caddy route exists (may have been missed during deploy)
    port = 80
    if sd.app_type:
        meta = AppManager(settings.apps_dir).get_template_info(sd.app_type)
        port = meta.get("default_port", 80)
    try:
        await caddy.add_subdomain(sd.subdomain, base_domain, port=port)
    except Exception as e:
        logger.warning(f"Caddy route add failed for {fqdn}: {e}")

    # Step 2: reload config to trigger certificate provisioning
    try:
        r = await caddy.renew_certificate(fqdn)
        if r.get("success"):
            return HTMLResponse(
                '<span class="text-green-600 text-xs font-medium">SSL renewed ✓</span>'
            )
        return HTMLResponse(
            f'<span class="text-red-500 text-xs">Failed: {r.get("error", "?")}</span>'
        )
    except Exception as e:
        logger.error(f"SSL renew failed for {fqdn}: {e}")
        return HTMLResponse(f'<span class="text-red-500 text-xs">Error: {e}</span>')


@router.post("/apps/{sd_id}/stop", response_class=HTMLResponse)
async def app_stop(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)

    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

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
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

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
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

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
        from pit_panel.core.notifier import notify_app_delete

        await notify_app_delete(sd.subdomain, old_app_type or "unknown")
    return RedirectResponse("/apps", status_code=302)

"""App deployment wizard routes."""

import contextlib
import datetime
import logging
import os
import re

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
from pit_panel.web.router import router

logger = logging.getLogger(__name__)


def _get_db_password(settings, subdomain: str) -> str | None:
    env_path = os.path.join(settings.apps_dir, subdomain, ".env")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("WORDPRESS_DB_PASSWORD=") or line.startswith("DB_PASSWORD="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Failed to read db password from {env_path}: {e}")
    return None


def _has_db_container(settings, subdomain: str) -> bool:
    compose_path = os.path.join(settings.apps_dir, subdomain, "docker-compose.yml")
    try:
        with open(compose_path) as f:
            content = f.read().lower()
        return "mysql" in content or "mariadb" in content or "postgres" in content
    except Exception as e:
        logger.warning(f"Failed to read docker-compose for {subdomain}: {e}")
        return False


@router.get("/apps", response_class=HTMLResponse)
async def apps_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
    subdomains = result.scalars().all()
    mgr = AppManager()
    templates = mgr.list_templates()
    template_infos = [{"name": t, "meta": mgr.get_template_info(t)} for t in templates]

    return render(
        "apps.html",
        user=user,
        settings=settings,
        subdomains=subdomains,
        templates=templates,
        template_infos=template_infos,
        error=None,
    )


@router.post("/apps/deploy", response_class=HTMLResponse)
async def app_deploy(
    request: Request,
    subdomain_id: int = Form(-1),
    new_subdomain: str = Form(""),
    stack_type: str = Form(...),
    port: int = Form(8000),
    is_main_domain: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    mgr = AppManager(settings.apps_dir)
    docker_mgr = DockerManager(settings.apps_dir)

    sd = None
    error = None

    # Resolve subdomain: use existing by ID or create new
    if is_main_domain:
        if not settings.base_domain:
            error = "Base domain not configured. Set it in Settings."
        else:
            existing = await db.execute(
                select(Subdomain).where(
                    Subdomain.is_main_domain,
                    Subdomain.base_domain == settings.base_domain,
                )
            )
            sd = existing.scalar_one_or_none()
            if sd:
                if sd.app_type:
                    error = "Main domain app already deployed"
            else:
                sd = Subdomain(
                    subdomain="_main_",
                    base_domain=settings.base_domain,
                    owner_user_id=user.id,
                    is_main_domain=True,
                )
                db.add(sd)
                await db.flush()
    elif subdomain_id > 0:
        result = await db.execute(select(Subdomain).where(Subdomain.id == subdomain_id))
        sd = result.scalar_one_or_none()
        if not sd:
            error = "Subdomain not found"
    elif new_subdomain.strip():
        name = new_subdomain.strip().lower().replace(" ", "-")
        if not re.fullmatch(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", name):
            error = f"Invalid subdomain name: {name}"
        else:
            if not settings.base_domain:
                error = "Base domain not configured. Set it in Settings."
            else:
                existing = await db.execute(
                    select(Subdomain).where(
                        Subdomain.subdomain == name,
                        Subdomain.base_domain == settings.base_domain,
                    )
                )
                sd = existing.scalar_one_or_none()
                if not sd:
                    sd = Subdomain(
                        subdomain=name,
                        base_domain=settings.base_domain,
                        owner_user_id=user.id,
                    )
                    db.add(sd)
                    await db.flush()
    else:
        error = "Select an existing subdomain or enter a new name"

    if error or not sd:
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        mgr2 = AppManager()
        templates = mgr2.list_templates()
        template_infos = [{"name": t, "meta": mgr2.get_template_info(t)} for t in templates]
        return render(
            "apps.html",
            user=user,
            settings=settings,
            subdomains=subdomains,
            templates=templates,
            template_infos=template_infos,
            error=error,
        )

    # Deploy template
    try:
        mgr.deploy_template(sd.subdomain, stack_type, variables={"PORT": str(port)})
    except ValueError as e:
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        mgr2 = AppManager()
        tpls = mgr2.list_templates()
        infos = [{"name": t, "meta": mgr2.get_template_info(t)} for t in tpls]
        return render(
            "apps.html",
            user=user,
            settings=settings,
            subdomains=subdomains,
            templates=tpls,
            template_infos=infos,
            error=str(e),
        )

    # Docker compose up
    compose_ok = False
    try:
        result = await docker_mgr.compose_up(sd.subdomain)
        compose_ok = result.get("success", False)
        if not compose_ok:
            error = f"Docker compose failed: {result.get('stderr', '')[:300]}"
    except Exception as e:
        error = f"Docker compose error: {e}"

    # Caddy route
    if settings.base_domain:
        try:
            caddy = CaddyManager(settings.caddy_admin_url)
            if sd.is_main_domain:
                await caddy.add_main_domain(settings.base_domain, port=port)
            elif sd.app_type != stack_type:
                await caddy.add_subdomain(sd.subdomain, settings.base_domain)
        except Exception as e:
            logger.error(f"Caddy route error for {sd.subdomain}: {e}")
            error = (error or "") + f" | Caddy route error: {e}"

    sd.app_type = stack_type
    sd.last_deployed = datetime.datetime.now(datetime.UTC)

    deployment = AppDeployment(
        subdomain_id=sd.id,
        stack_type=stack_type,
        compose_path=f"{settings.apps_dir}/{sd.subdomain}/docker-compose.yml",
        status="running" if compose_ok else "failed",
    )
    db.add(deployment)

    db.add(
        AuditLog(
            user_id=user.id,
            action="app_deploy",
            target_type="subdomain",
            target_id=sd.id,
            details={"stack": stack_type, "subdomain": sd.subdomain, "success": compose_ok},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    if error:
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        mgr2 = AppManager()
        templates = mgr2.list_templates()
        template_infos = [{"name": t, "meta": mgr2.get_template_info(t)} for t in templates]
        return render(
            "apps.html",
            user=user,
            settings=settings,
            subdomains=subdomains,
            templates=templates,
            template_infos=template_infos,
            error=error,
        )

    return RedirectResponse(f"/apps/{sd.id}", status_code=302)


@router.get("/apps/{sd_id}", response_class=HTMLResponse)
async def app_detail(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return RedirectResponse("/apps", status_code=302)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    containers = []
    with contextlib.suppress(Exception):
        containers = await docker_mgr.compose_ps(sd.subdomain)

    logs = ""
    try:
        logs = await docker_mgr.compose_logs(sd.subdomain, tail=50)
    except Exception as e:
        logger.error(f"Failed to fetch logs for {sd.subdomain}: {e}")
        logs = "Error fetching logs"

    mgr = AppManager()
    app_info = mgr.get_template_info(sd.app_type) if sd.app_type else {}

    needs_db = sd.app_type in ("wordpress", "ghost")
    db_password = _get_db_password(settings, sd.subdomain) if needs_db else None
    has_db = _has_db_container(settings, sd.subdomain)

    return render(
        "app_detail.html",
        user=user,
        sd=sd,
        containers=containers,
        logs=logs,
        app_info=app_info,
        db_password=db_password,
        db_container=has_db,
        app_version=app_info.get("version", ""),
        app_port=app_info.get("default_port", ""),
    )


@router.post("/apps/{sd_id}/restart", response_class=HTMLResponse)
async def app_restart(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.compose_restart(sd.subdomain)
    return RedirectResponse(f"/apps/{sd_id}", status_code=302)


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
        await docker_mgr.compose_down(sd.subdomain)
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
        await docker_mgr.compose_down(sd.subdomain, remove_volumes=True)

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


@router.get("/apps/{sd_id}/env", response_class=HTMLResponse)
async def app_env_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

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
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return "<div class='text-red-500'>App not found</div>"

    settings = get_settings()
    env_path = os.path.join(settings.apps_dir, sd.subdomain, ".env")

    error = None
    success = None
    try:
        with open(env_path, "w") as f:
            # Basic sanitization
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

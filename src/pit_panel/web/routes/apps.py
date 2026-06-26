"""App deployment wizard routes."""

import contextlib
import datetime
import os

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.app_manager import AppManager
from pit_panel.core.docker_ops import DockerManager
from pit_panel.db.models import AppDeployment, AuditLog, Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render
from pit_panel.web.router import router


def _get_db_password(settings, subdomain: str) -> str | None:
    env_path = os.path.join(settings.apps_dir, subdomain, ".env")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("WORDPRESS_DB_PASSWORD=") or line.startswith("DB_PASSWORD="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _has_db_container(settings, subdomain: str) -> bool:
    compose_path = os.path.join(settings.apps_dir, subdomain, "docker-compose.yml")
    try:
        with open(compose_path) as f:
            content = f.read()
        c = content.lower()
        return "mysql" in c or "mariadb" in c or "postgres" in c
    except Exception:
        return False


@router.get("/apps", response_class=HTMLResponse)
async def apps_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
    subdomains = result.scalars().all()
    mgr = AppManager()
    templates = mgr.list_templates()
    template_infos = [{"name": t, "meta": mgr.get_template_info(t)} for t in templates]

    return render(
        "apps.html",
        user=user,
        subdomains=subdomains,
        templates=templates,
        template_infos=template_infos,
        error=None,
    )


@router.post("/apps/deploy", response_class=HTMLResponse)
async def app_deploy(
    request: Request,
    subdomain_id: int = Form(...),
    stack_type: str = Form(...),
    port: int = Form(8000),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == subdomain_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return RedirectResponse("/apps", status_code=302)

    settings = get_settings()
    mgr = AppManager(settings.apps_dir)
    docker_mgr = DockerManager(settings.apps_dir)

    try:
        mgr.deploy_template(sd.subdomain, stack_type, variables={"PORT": str(port)})
    except ValueError:
        mgr2 = AppManager()
        templates = mgr2.list_templates()
        template_infos = [{"name": t, "meta": mgr2.get_template_info(t)} for t in templates]
        result2 = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result2.scalars().all()
        return render(
            "apps.html",
            user=user,
            subdomains=subdomains,
            templates=templates,
            template_infos=template_infos,
            error="Invalid stack type",
        )

    with contextlib.suppress(Exception):
        await docker_mgr.compose_up(sd.subdomain)

    sd.app_type = stack_type
    sd.last_deployed = datetime.datetime.now(datetime.UTC)

    deployment = AppDeployment(
        subdomain_id=sd.id,
        stack_type=stack_type,
        compose_path=f"{settings.apps_dir}/{sd.subdomain}/docker-compose.yml",
        status="running",
    )
    db.add(deployment)

    entry = AuditLog(
        user_id=user.id,
        action="app_deploy",
        target_type="subdomain",
        target_id=sd.id,
        details={"stack": stack_type, "subdomain": sd.subdomain},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(entry)
    await db.commit()

    return RedirectResponse("/apps", status_code=302)


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
        app_info=app_info,
        db_password=db_password,
        db_container=has_db,
        app_version=app_info.get("version", ""),
        app_port=app_info.get("default_port", ""),
    )


@router.get("/apps/{sd_id}/containers", response_class=HTMLResponse)
async def app_containers_tab(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("Not found", status_code=404)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    containers = []
    with contextlib.suppress(Exception):
        containers = await docker_mgr.compose_ps(sd.subdomain)

    return render("tabs/_containers.html", sd=sd, containers=containers)


@router.get("/apps/{sd_id}/backup", response_class=HTMLResponse)
async def app_backup_tab(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("Not found", status_code=404)

    return render("tabs/_backup.html", sd=sd)


@router.get("/apps/{sd_id}/logs", response_class=HTMLResponse)
async def app_logs_tab(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("Not found", status_code=404)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    logs = ""
    try:
        logs = await docker_mgr.compose_logs(sd.subdomain, tail=100)
    except Exception:
        logs = "Error fetching logs"

    return render("tabs/_logs.html", sd=sd, logs=logs)


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

        entry = AuditLog(
            user_id=user.id,
            action="app_stop",
            target_type="subdomain",
            target_id=sd.id,
            details={"subdomain": sd.subdomain},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(entry)
        await db.commit()

    return RedirectResponse("/apps", status_code=302)


@router.post("/apps/{sd_id}/wp/flush-cache", response_class=HTMLResponse)
async def wp_flush_cache(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("Not found", status_code=404)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    try:
        proc = await docker_mgr._run_compose(
            ["exec", "-T", "wordpress", "wp", "cache", "flush"], sd.subdomain
        )
        msg = proc.get("stdout", "").strip() or proc.get("stderr", "").strip() or "Cache flushed"
    except Exception as e:
        msg = f"Error: {e}"

    return HTMLResponse(f'<div class="text-sm text-green-600 dark:text-green-400 mt-2">{msg}</div>')


@router.post("/apps/{sd_id}/wp/update-plugins", response_class=HTMLResponse)
async def wp_update_plugins(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("Not found", status_code=404)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    try:
        proc = await docker_mgr._run_compose(
            ["exec", "-T", "wordpress", "wp", "plugin", "update", "--all"], sd.subdomain
        )
        stdout = proc.get("stdout", "").strip()
        stderr = proc.get("stderr", "").strip()
        msg = stdout or stderr or "Plugins updated"
        msg = msg[:500]
    except Exception as e:
        msg = f"Error: {e}"

    cls = "text-xs text-green-600 dark:text-green-400 mt-2 whitespace-pre-wrap"
    return HTMLResponse(f'<pre class="{cls}">{msg}</pre>')


@router.post("/apps/{sd_id}/wp/update-core", response_class=HTMLResponse)
async def wp_update_core(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("Not found", status_code=404)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    try:
        proc = await docker_mgr._run_compose(
            ["exec", "-T", "wordpress", "wp", "core", "update"], sd.subdomain
        )
        stdout = proc.get("stdout", "").strip()
        stderr = proc.get("stderr", "").strip()
        msg = stdout or stderr or "WordPress updated"
        msg = msg[:500]
    except Exception as e:
        msg = f"Error: {e}"

    cls = "text-xs text-green-600 dark:text-green-400 mt-2 whitespace-pre-wrap"
    return HTMLResponse(f'<pre class="{cls}">{msg}</pre>')

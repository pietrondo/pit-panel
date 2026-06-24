"""App deployment wizard routes."""

import contextlib

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.app_manager import AppManager
from pit_panel.core.docker_ops import DockerManager
from pit_panel.db.models import AppDeployment, AuditLog, Subdomain, User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token
from pit_panel.web.render import render
from pit_panel.web.router import router


async def _get_user(request: Request, db: AsyncSession) -> User | None:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    data = unsign_session_token(settings, cookie)
    if not data:
        return None
    result = await db.execute(select(User).where(User.id == data.get("uid")))
    return result.scalar_one_or_none()


@router.get("/apps", response_class=HTMLResponse)
async def apps_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
    subdomains = result.scalars().all()
    templates = AppManager().list_templates()

    return render(
        "apps.html", user=user, subdomains=subdomains, templates=templates, error=None
    )


@router.post("/apps/deploy", response_class=HTMLResponse)
async def app_deploy(
    request: Request,
    subdomain_id: int = Form(...),
    stack_type: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(request, db)
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
        mgr.deploy_template(sd.subdomain, stack_type)
    except ValueError:
        templates = AppManager().list_templates()
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        return render(
            "apps.html",
            user=user,
            subdomains=subdomains,
            templates=templates,
            error="Invalid stack type",
        )

    with contextlib.suppress(Exception):
        await docker_mgr.compose_up(sd.subdomain)

    sd.app_type = stack_type
    sd.last_deployed = __import__("datetime").datetime.now(__import__("datetime").UTC)

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


@router.post("/apps/{sd_id}/stop", response_class=HTMLResponse)
async def app_stop(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await _get_user(request, db)
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

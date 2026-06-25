import typing

"""Container management routes with live state and logs."""

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.docker_ops import DockerManager
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render
from pit_panel.web.router import router


@router.get("/containers", response_class=HTMLResponse)
async def containers_list(request: Request, db: AsyncSession = Depends(get_db)) -> typing.Any:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    result = await db.execute(select(Subdomain).where(Subdomain.app_type.isnot(None)))
    subdomains = result.scalars().all()

    containers_data = {}
    for sd in subdomains:
        try:
            containers = await docker_mgr.compose_ps(sd.subdomain)
        except Exception:
            containers = []
        containers_data[sd.id] = containers

    return render(
        "containers.html",
        user=user,
        subdomains=subdomains,
        containers_data=containers_data,
    )


@router.get("/containers/{sd_id}/logs", response_class=HTMLResponse)
async def container_logs(
    request: Request, sd_id: int, db: AsyncSession = Depends(get_db)
) -> typing.Any:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return RedirectResponse("/containers", status_code=302)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    try:
        logs = await docker_mgr.compose_logs(sd.subdomain, tail=200)
    except Exception:
        logs = "Error fetching logs"

    return render("container_logs.html", user=user, subdomain=sd, logs=logs)


@router.post("/containers/{sd_id}/restart", response_class=HTMLResponse)
async def container_restart(
    request: Request, sd_id: int, db: AsyncSession = Depends(get_db)
) -> typing.Any:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.compose_restart(sd.subdomain)

    return RedirectResponse("/containers", status_code=302)

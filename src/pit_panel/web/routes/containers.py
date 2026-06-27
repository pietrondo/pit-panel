"""Container management routes with live state and logs."""

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.docker_ops import DockerManager
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

router = APIRouter()


@router.get("/containers", response_class=HTMLResponse)
async def containers_list(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    all_containers = await docker_mgr.ps_all()

    result = await db.execute(select(Subdomain).where(Subdomain.app_type.isnot(None)))
    subdomains = {sd.subdomain: sd for sd in result.scalars().all()}

    containers_data: dict[int, list[dict[str, Any]]] = {}
    orphan_containers: list[dict[str, Any]] = []

    for c in all_containers:
        if "Name" not in c and "Names" in c:
            c["Name"] = c["Names"]

        labels = c.get("Labels", "") or ""
        project = ""
        for part in labels.split(","):
            part = part.strip()
            if part.startswith("com.docker.compose.project="):
                project = part.split("=", 1)[1]
                break

        if project and project in subdomains:
            sd = subdomains[project]
            containers_data.setdefault(sd.id, []).append(c)
        else:
            orphan_containers.append(c)

    return render(
        "containers.html",
        user=user,
        subdomains=list(subdomains.values()),
        containers_data=containers_data,
        orphan_containers=orphan_containers,
    )


@router.get("/containers/{sd_id}/logs", response_class=HTMLResponse)
async def container_logs(
    request: Request, sd_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
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
) -> Response:
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


@router.post("/containers/container/{container_id}/stop")
async def container_stop(
    request: Request, container_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    await docker_mgr.container_stop(container_id)
    return RedirectResponse("/containers", status_code=302)


@router.post("/containers/container/{container_id}/start")
async def container_start(
    request: Request, container_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    await docker_mgr.container_start(container_id)
    return RedirectResponse("/containers", status_code=302)


@router.get("/containers/container/{container_id}/logs", response_class=HTMLResponse)
async def container_logs_live(
    request: Request, container_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    try:
        logs = await docker_mgr.container_logs_live(container_id, tail=200)
    except Exception:
        logs = "Error fetching logs"
    return render(
        "container_logs.html",
        user=user,
        logs=logs,
        subdomain=None,
        container_id=container_id,
    )


@router.get("/containers/container/{container_id}/stats")
async def container_stats(
    request: Request, container_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    try:
        stats = await docker_mgr.container_stats(container_id)
    except Exception:
        stats = {}
    return render("container_stats.html", stats=stats, container_id=container_id)

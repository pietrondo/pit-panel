"""Container management routes with live state and logs."""

import asyncio
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.docker_ops import DockerManager
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render
from pit_panel.web.routes.app_routes.access import require_subdomain_access

router = APIRouter()


_CONTAINERS_CACHE: dict[str, tuple[float, Any]] = {}
MAX_CACHE_SIZE = 100


def _compose_project(container: dict[str, Any]) -> str:
    labels = container.get("Labels", "") or ""
    for part in labels.split(","):
        part = part.strip()
        if part.startswith("com.docker.compose.project="):
            return part.split("=", 1)[1]
    return ""


def _filter_owned(
    user,
    subdomains: dict[str, Subdomain],
    containers_data: dict[int, list[dict[str, Any]]],
    orphan_containers: list[dict[str, Any]],
):
    """Non-admins only see their own apps; containers with no owner are admin-only."""
    if bool(getattr(user, "is_admin", False)):
        return subdomains, containers_data, orphan_containers
    owned = {name: sd for name, sd in subdomains.items() if sd.owner_user_id == user.id}
    owned_ids = {sd.id for sd in owned.values()}
    return owned, {sid: c for sid, c in containers_data.items() if sid in owned_ids}, []


async def _require_container_access(
    user, db: AsyncSession, docker_mgr: DockerManager, container_id: str
) -> None:
    """A container may only be touched by its owner; orphans are admin-only."""
    project = ""
    try:
        containers = await docker_mgr.ps_all()
    except Exception:
        containers = []
    for container in containers:
        cid = container.get("Id", "") or ""
        names = container.get("Names", "") or container.get("Name", "") or ""
        if (cid and cid.startswith(container_id)) or container_id in names:
            project = _compose_project(container)
            break
    sd = None
    if project:
        result = await db.execute(select(Subdomain).where(Subdomain.subdomain == project))
        sd = result.scalar_one_or_none()
    if sd is None:
        if not bool(getattr(user, "is_admin", False)):
            raise HTTPException(status_code=403, detail="Administrator privileges required")
        return
    require_subdomain_access(user, sd)


async def _get_containers_data(
    db: AsyncSession, docker_mgr: DockerManager
) -> tuple[dict[str, Subdomain], dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    now = time.monotonic()
    if "containers_data" in _CONTAINERS_CACHE:
        cached_at, value = _CONTAINERS_CACHE["containers_data"]
        if now - cached_at < 5.0:
            return value

    async def _fetch_subdomains():
        result = await db.execute(select(Subdomain).where(Subdomain.app_type.isnot(None)))
        return result.scalars().all()

    docker_task = asyncio.create_task(docker_mgr.ps_all())
    subdomains_task = asyncio.create_task(_fetch_subdomains())
    tasks = (docker_task, subdomains_task)

    try:
        all_containers, result_subdomains = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    subdomains = {sd.subdomain: sd for sd in result_subdomains}

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

    res = (subdomains, containers_data, orphan_containers)

    if len(_CONTAINERS_CACHE) >= MAX_CACHE_SIZE:
        _CONTAINERS_CACHE.clear()

    _CONTAINERS_CACHE["containers_data"] = (now, res)
    return res


@router.get("/containers/fragment", response_class=HTMLResponse)
async def containers_fragment(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    subdomains, containers_data, orphan_containers = await _get_containers_data(db, docker_mgr)
    subdomains, containers_data, orphan_containers = _filter_owned(
        user, subdomains, containers_data, orphan_containers
    )

    return HTMLResponse(  # noqa: E501
        '<div id="containers-list-wrapper" hx-get="/containers/fragment" hx-trigger="every 15s" hx-swap="outerHTML">'  # noqa: E501
        + render(
            "tabs/_containers_list.html",
            request=request,
            user=user,
            subdomains=list(subdomains.values()),
            containers_data=containers_data,
            orphan_containers=orphan_containers,
        ).body.decode()
        + "</div>"
    )


@router.get("/containers", response_class=HTMLResponse)
async def containers_list(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await get_user(request, db)

    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    subdomains, containers_data, orphan_containers = await _get_containers_data(db, docker_mgr)
    subdomains, containers_data, orphan_containers = _filter_owned(
        user, subdomains, containers_data, orphan_containers
    )

    return render(
        "containers.html",
        request=request,
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
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return RedirectResponse("/containers", status_code=302)
    require_subdomain_access(user, sd)

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
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        require_subdomain_access(user, sd)
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.run_compose_command(sd.subdomain, ["restart"])

    return RedirectResponse("/containers", status_code=302)


@router.post("/containers/container/{container_id}/stop")
async def container_stop(
    request: Request, container_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user(request, db)
    if not re.fullmatch(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", container_id):
        return HTMLResponse("Invalid container ID", status_code=400)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    await _require_container_access(user, db, docker_mgr, container_id)
    await docker_mgr.container_stop(container_id)
    return RedirectResponse("/containers", status_code=302)


@router.post("/containers/container/{container_id}/start")
async def container_start(
    request: Request, container_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user(request, db)
    if not re.fullmatch(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", container_id):
        return HTMLResponse("Invalid container ID", status_code=400)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    await _require_container_access(user, db, docker_mgr, container_id)
    await docker_mgr.container_start(container_id)
    return RedirectResponse("/containers", status_code=302)


@router.get("/containers/container/{container_id}/logs", response_class=HTMLResponse)
async def container_logs_live(
    request: Request, container_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user(request, db)
    if not re.fullmatch(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", container_id):
        return HTMLResponse("Invalid container ID", status_code=400)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    await _require_container_access(user, db, docker_mgr, container_id)
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
    if not re.fullmatch(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", container_id):
        return HTMLResponse("Invalid container ID", status_code=400)
    if not user:
        return RedirectResponse("/login", status_code=302)
    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    await _require_container_access(user, db, docker_mgr, container_id)
    try:
        stats = await docker_mgr.container_stats(container_id)
    except Exception:
        stats = {}
    return render("container_stats.html", stats=stats, container_id=container_id)

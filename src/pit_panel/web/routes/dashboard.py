"""Dashboard with live system stats."""

import os
import platform
import shutil

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

router = APIRouter()


def _disk_usage() -> str:
    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        pct = (1 - free_gb / total_gb) * 100
        return f"{free_gb:.0f}G free / {total_gb:.0f}G ({pct:.0f}%)"
    except Exception:
        return "N/A"


def _server_hostname() -> str:
    try:
        return platform.node() or "unknown"
    except Exception:
        return "unknown"


def _cpu_usage() -> dict:
    try:
        with open("/proc/loadavg") as f:
            load = float(f.read().split()[0])
            cores = os.cpu_count() or 1
            pct = min(round((load / cores) * 100), 100)
            return {"load_1m": load, "cores": cores, "pct": pct}
    except Exception:
        return {"load_1m": 0, "cores": os.cpu_count() or 1, "pct": 0}


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()

    subdomains_result = await db.execute(select(Subdomain).limit(20))
    subdomains = subdomains_result.scalars().all()

    # Use a single query with conditional aggregation to get both counts efficiently
    row = (
        await db.execute(
            select(
                func.count(Subdomain.id).label("total"),
                func.count(Subdomain.id).filter(Subdomain.app_type.isnot(None)).label("running"),
            )
        )
    ).first()

    total_subdomains = row.total if row else 0
    apps_running = row.running if row else 0

    return render(
        "dashboard.html",
        user=user,
        subdomains=subdomains,
        settings=settings,
        stats={
            "subdomain_count": total_subdomains,
            "apps_running": apps_running,
            "disk_usage": _disk_usage(),
            "cpu": _cpu_usage(),
        },
    )

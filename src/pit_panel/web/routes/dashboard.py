"""Dashboard with live system stats."""

import os
import shutil

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render
from pit_panel.web.router import router


def _disk_usage() -> str:
    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        pct = (1 - free_gb / total_gb) * 100
        return f"{free_gb:.0f}G free / {total_gb:.0f}G ({pct:.0f}%)"
    except Exception:
        return "N/A"


def _cpu_usage() -> str:
    try:
        with open("/proc/loadavg") as f:
            load = f.read().split()[:3]
            cores = os.cpu_count() or 1
            return f"load {load[0]} ({cores} cores)"
    except Exception:
        try:
            return f"{os.cpu_count() or '?'} cores"
        except Exception:
            return "N/A"


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()

    subdomains_result = await db.execute(select(Subdomain).limit(20))
    subdomains = subdomains_result.scalars().all()

    apps_count = sum(1 for sd in subdomains if sd.app_type)

    return render(
        "dashboard.html",
        user=user,
        subdomains=subdomains,
        settings=settings,
        stats={
            "subdomain_count": len(subdomains),
            "apps_running": apps_count,
            "disk_usage": _disk_usage(),
            "cpu": _cpu_usage(),
        },
    )

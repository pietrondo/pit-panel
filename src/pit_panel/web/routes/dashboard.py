import typing

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


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> typing.Any:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()

    subdomains_result = await db.execute(select(Subdomain).limit(20))
    subdomains = subdomains_result.scalars().all()

    return render(
        "dashboard.html",
        user=user,
        subdomains=subdomains,
        settings=settings,
        stats={
            "subdomain_count": len(subdomains),
            "apps_running": 0,
            "disk_usage": "N/A",
            "cpu": "N/A",
        },
    )

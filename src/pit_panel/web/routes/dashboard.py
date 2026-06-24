from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import Subdomain, User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token
from pit_panel.web.render import render
from pit_panel.web.router import router


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return RedirectResponse("/login", status_code=302)
    data = unsign_session_token(settings, cookie)
    if not data:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(User).where(User.id == data.get("uid")))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse("/login", status_code=302)

    subdomains_result = await db.execute(select(Subdomain).limit(20))
    subdomains = subdomains_result.scalars().all()

    return render(
        "dashboard.html",
        user=user,
        subdomains=subdomains,
        stats={
            "subdomain_count": len(subdomains),
            "apps_running": 0,
            "disk_usage": "N/A",
            "cpu": "N/A",
        },
    )

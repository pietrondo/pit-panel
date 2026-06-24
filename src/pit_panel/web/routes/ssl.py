"""SSL certificate management routes via Caddy admin API."""

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.db.models import User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token
from pit_panel.web.render import render
from pit_panel.web.router import router


async def _get_admin(request: Request, db: AsyncSession) -> User | None:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    data = unsign_session_token(settings, cookie)
    if not data:
        return None
    result = await db.execute(select(User).where(User.id == data.get("uid")))
    user = result.scalar_one_or_none()
    if user and user.is_admin:
        return user
    return None


@router.get("/ssl", response_class=HTMLResponse)
async def ssl_overview(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    caddy = CaddyManager(settings.caddy_admin_url)
    certs = await caddy.get_certificates()

    return render("ssl.html", user=user, certs=certs, renew_result=None)


@router.post("/ssl/renew", response_class=HTMLResponse)
async def ssl_renew(
    request: Request,
    domain: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    caddy = CaddyManager(settings.caddy_admin_url)
    result = await caddy.renew_certificate(domain)

    certs = await caddy.get_certificates()
    return render(
        "ssl.html",
        user=user,
        certs=certs,
        renew_result=result,
    )

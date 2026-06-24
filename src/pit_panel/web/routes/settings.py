"""Settings and audit log routes."""


from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import AuditLog, User
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


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50)
    )
    audit_entries = result.scalars().all()

    return render(
        "settings.html",
        user=user,
        audit_entries=audit_entries,
        settings=get_settings(),
    )


@router.get("/settings/audit", response_class=HTMLResponse)
async def audit_log(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100)
    )
    entries = result.scalars().all()

    return render("audit.html", user=user, entries=entries)

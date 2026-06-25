"""Security overview: IP bans, login attempts, active sessions."""

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.db.models import LoginAttempt, User
from pit_panel.db.models import Session as DBSession
from pit_panel.db.session import get_db
from pit_panel.security.ipban import get_banned_ips, unban_ip
from pit_panel.web.auth import revoke_session
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render
from pit_panel.web.router import router


@router.get("/security", response_class=HTMLResponse)
async def security_overview(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    bans = await get_banned_ips(db)
    result = await db.execute(
        select(LoginAttempt).order_by(LoginAttempt.attempted_at.desc()).limit(50)
    )
    attempts = result.scalars().all()

    ses_result = await db.execute(
        select(DBSession, User.username)
        .join(User, DBSession.user_id == User.id)
        .order_by(DBSession.created_at.desc())
    )
    active_sessions = []
    for sess, uname in ses_result:
        active_sessions.append(
            {
                "id": sess.id,
                "username": uname,
                "ip": sess.ip,
                "created": sess.created_at,
            }
        )

    return render(
        "security.html",
        user=user,
        bans=bans,
        attempts=attempts,
        sessions=active_sessions,
        unban_result=None,
    )


@router.post("/security/unban", response_class=HTMLResponse)
async def security_unban(
    request: Request,
    ip: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = None
    if ip:
        ok = await unban_ip(db, ip, user.id)
        result = {"ip": ip, "success": ok}

    bans = await get_banned_ips(db)
    attempts_result = await db.execute(
        select(LoginAttempt).order_by(LoginAttempt.attempted_at.desc()).limit(50)
    )
    attempts = attempts_result.scalars().all()

    ses_result = await db.execute(
        select(DBSession, User.username)
        .join(User, DBSession.user_id == User.id)
        .order_by(DBSession.created_at.desc())
    )
    active_sessions = []
    for sess, uname in ses_result:
        active_sessions.append(
            {
                "id": sess.id,
                "username": uname,
                "ip": sess.ip,
                "created": sess.created_at,
            }
        )

    return render(
        "security.html",
        user=user,
        bans=bans,
        attempts=attempts,
        sessions=active_sessions,
        unban_result=result,
    )


@router.post("/security/revoke-session", response_class=HTMLResponse)
async def security_revoke_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    session_id = int(form.get("session_id", 0))
    if session_id:
        await revoke_session(db, session_id)

    return RedirectResponse("/security", status_code=302)

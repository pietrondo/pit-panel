import base64
import datetime
import io

import qrcode
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import Session as DBSession
from pit_panel.db.models import User
from pit_panel.db.session import get_db
from pit_panel.security.crypto import hash_token, verify_password
from pit_panel.security.ipban import record_login_attempt
from pit_panel.security.totp import generate_totp_secret, get_totp_uri, verify_totp
from pit_panel.web.auth import (
    SESSION_COOKIE,
    create_session_record,
    create_session_token,
    revoke_session,
    unsign_session_token,
)
from pit_panel.web.deps import get_user
from pit_panel.web.limiter import limiter
from pit_panel.web.render import render

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie and unsign_session_token(get_settings(), cookie):
        return RedirectResponse("/", status_code=302)
    return render("login.html", error=None)


@router.post("/login", response_class=HTMLResponse)
@limiter.limit("5/minute")  # type: ignore
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    totp_code: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    settings = get_settings()
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        ip = request.client.host if request.client else "unknown"
        await record_login_attempt(db, ip, username, False)
        from pit_panel.core.notifier import notify_login_failed

        await notify_login_failed(username, ip)
        return render("login.html", error="Invalid credentials")

    if user.totp_enabled:
        form_data = await request.form()
        totp_code_str = str(form_data.get("totp_code")) if form_data.get("totp_code") else None
        totp_code = totp_code_str
        if not totp_code:
            return render("login.html", totp_required=True, username=username, error=None)
        if not verify_totp(user.totp_secret or "", totp_code):
            await record_login_attempt(
                db, request.client.host if request.client else "unknown", username, False
            )
            return render(
                "login.html",
                totp_required=True,
                username=username,
                error="Invalid TOTP code",
            )

    raw, _ = create_session_token(settings, user.id, 0)
    session_id = await create_session_record(
        db,
        user.id,
        hash_token(raw),
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
        settings,
    )
    _, final_cookie = create_session_token(settings, user.id, session_id, raw=raw)

    # Fix: update session token_hash to match cookie
    data = unsign_session_token(settings, final_cookie)
    if data:
        await db.execute(
            update(DBSession).where(DBSession.id == session_id).values(token_hash=data["tok"])
        )

    user.last_login = datetime.datetime.now(datetime.UTC)
    await db.commit()

    ip = request.client.host if request.client else "unknown"
    await record_login_attempt(db, ip, username, True)
    from pit_panel.core.notifier import notify_login_success

    await notify_login_success(username, ip)

    resp = RedirectResponse("/", status_code=302)
    is_https = request.url.scheme == "https" or (
        request.headers.get("x-forwarded-proto", "") == "https"
    )
    resp.set_cookie(
        SESSION_COOKIE,
        final_cookie,
        httponly=True,
        secure=is_https,
        samesite="strict" if is_https else "lax",
        max_age=settings.session_duration_hours * 3600,
    )
    return resp


@router.get("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        data = unsign_session_token(get_settings(), cookie)
        if data:
            await revoke_session(db, data.get("sid", 0))
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("/setup-2fa", response_class=HTMLResponse)
async def setup_2fa_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not user.totp_secret:
        user.totp_secret = generate_totp_secret()
        await db.commit()

    uri = get_totp_uri(user.totp_secret, user.username)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf)
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render("setup_2fa.html", totp_secret=user.totp_secret, qr_code=qr_b64, error=None)


@router.post("/setup-2fa", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def setup_2fa_post(
    request: Request,
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)
    if not user or not user.totp_secret:
        return RedirectResponse("/login", status_code=302)

    if not verify_totp(user.totp_secret, str(code)):
        import base64 as b64
        import io as io_mod

        import qrcode as qr

        uri = get_totp_uri(user.totp_secret, user.username)
        img = qr.make(uri)
        buf = io_mod.BytesIO()
        img.save(buf)
        qr_b64 = b64.b64encode(buf.getvalue()).decode()
        return render(
            "setup_2fa.html",
            totp_secret=user.totp_secret,
            qr_code=qr_b64,
            error="Invalid code",
        )

    user.totp_enabled = True
    await db.commit()
    return RedirectResponse("/", status_code=302)

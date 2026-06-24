import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import Settings
from pit_panel.db.models import Subdomain, User
from pit_panel.db.session import get_db, init_db
from pit_panel.security.crypto import hash_token, verify_password
from pit_panel.security.totp import generate_totp_secret, verify_totp
from pit_panel.web.auth import (
    SESSION_COOKIE,
    create_session_record,
    create_session_token,
    revoke_session,
    unsign_session_token,
)

limiter = Limiter(key_func=get_remote_address)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings.from_config_file()

    app = FastAPI(
        title="pit-panel",
        version="0.1.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from jinja2 import Environment, FileSystemLoader

    templates = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    def render(name: str, **ctx) -> HTMLResponse:
        return HTMLResponse(templates.get_template(name).render(**ctx))

    def get_user_from_cookie(request: Request, db: AsyncSession) -> User | None:
        cookie = request.cookies.get(SESSION_COOKIE)
        if not cookie:
            return None
        data = unsign_session_token(settings, cookie)
        if not data:
            return None

        async def _validate():
            from pit_panel.web.auth import validate_session as vs

            return await vs(db, cookie, settings, data.get("uid", 0))

        import asyncio

        return asyncio.get_event_loop().run_until_complete(_validate())

    # --- Auth routes ---

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        cookie = request.cookies.get(SESSION_COOKIE)
        if cookie and unsign_session_token(settings, cookie):
            return RedirectResponse("/", status_code=302)
        return render("login.html", error=None)

    @app.post("/login", response_class=HTMLResponse)
    @limiter.limit("5/minute")
    async def login_post(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        db: AsyncSession = Depends(get_db),
    ):
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            return render("login.html", error="Invalid credentials")

        if user.totp_enabled:
            totp_code = (await request.form()).get("totp_code")
            if not totp_code:
                return render("login.html", totp_required=True, username=username, error=None)
            if not verify_totp(user.totp_secret or "", totp_code):
                return render(
                    "login.html",
                    totp_required=True,
                    username=username,
                    error="Invalid TOTP code",
                )

        raw, signed = create_session_token(settings, user.id, 0)
        session_id = await create_session_record(
            db, user.id, hash_token(raw), request.client.host if request.client else None,
            request.headers.get("user-agent"), settings,
        )
        raw2, signed2 = create_session_token(settings, user.id, session_id)
        await revoke_session(db, session_id)
        session_id2 = await create_session_record(
            db, user.id, hash_token(raw2), request.client.host if request.client else None,
            request.headers.get("user-agent"), settings,
        )
        raw3, signed3 = create_session_token(settings, user.id, session_id2)
        await revoke_session(db, session_id2)
        session_id3 = await create_session_record(
            db, user.id, hash_token(raw3), request.client.host if request.client else None,
            request.headers.get("user-agent"), settings,
        )
        _, final_cookie = create_session_token(settings, user.id, session_id3)

        user.last_login = datetime.datetime.now(datetime.UTC)
        await db.commit()

        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(
            SESSION_COOKIE,
            final_cookie,
            httponly=True,
            secure=not settings.debug,
            samesite="strict",
            max_age=settings.session_duration_hours * 3600,
        )
        return resp

    @app.get("/logout")
    async def logout(request: Request, db: AsyncSession = Depends(get_db)):
        cookie = request.cookies.get(SESSION_COOKIE)
        if cookie:
            data = unsign_session_token(settings, cookie)
            if data:
                await revoke_session(db, data.get("sid", 0))
        resp = RedirectResponse("/login", status_code=302)
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    @app.get("/setup-2fa", response_class=HTMLResponse)
    async def setup_2fa_page(request: Request, db: AsyncSession = Depends(get_db)):
        cookie = request.cookies.get(SESSION_COOKIE)
        if not cookie:
            return RedirectResponse("/login", status_code=302)
        data = unsign_session_token(settings, cookie)
        if not data:
            return RedirectResponse("/login", status_code=302)

        from sqlalchemy import select as sqla_select

        result = await db.execute(sqla_select(User).where(User.id == data.get("uid")))
        user = result.scalar_one_or_none()
        if not user:
            return RedirectResponse("/login", status_code=302)

        if not user.totp_secret:
            user.totp_secret = generate_totp_secret()
            await db.commit()

        import base64
        import io

        import qrcode

        from pit_panel.security.totp import get_totp_uri

        uri = get_totp_uri(user.totp_secret, user.username)
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        return render("setup_2fa.html", totp_secret=user.totp_secret, qr_code=qr_b64, error=None)

    @app.post("/setup-2fa", response_class=HTMLResponse)
    async def setup_2fa_post(
        request: Request,
        code: str = Form(...),
        db: AsyncSession = Depends(get_db),
    ):
        cookie = request.cookies.get(SESSION_COOKIE)
        if not cookie:
            return RedirectResponse("/login", status_code=302)
        data = unsign_session_token(settings, cookie)
        if not data:
            return RedirectResponse("/login", status_code=302)

        result = await db.execute(select(User).where(User.id == data.get("uid")))
        user = result.scalar_one_or_none()
        if not user or not user.totp_secret:
            return RedirectResponse("/login", status_code=302)

        if not verify_totp(user.totp_secret, code):
            import base64
            import io

            import qrcode

            from pit_panel.security.totp import get_totp_uri
            uri = get_totp_uri(user.totp_secret, user.username)
            img = qrcode.make(uri)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr_b64 = base64.b64encode(buf.getvalue()).decode()
            return render(
                "setup_2fa.html",
                totp_secret=user.totp_secret,
                qr_code=qr_b64,
                error="Invalid code",
            )

        user.totp_enabled = True
        await db.commit()
        return RedirectResponse("/", status_code=302)

    # --- Dashboard ---

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
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

        subdomain_count = await db.execute(select(Subdomain))
        subdomains = subdomain_count.scalars().all()

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

    # --- Health ---

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # --- Startup ---

    @app.on_event("startup")
    async def startup():
        await init_db(settings)

    return app

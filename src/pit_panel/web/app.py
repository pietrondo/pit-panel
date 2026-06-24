"""FastAPI application factory with security middleware."""

import contextlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from pit_panel.config import Settings, init_settings
from pit_panel.db.session import get_sessionmaker, init_db
from pit_panel.security.ipban import is_ip_banned
from pit_panel.web.router import router


async def _ip_ban_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            if await is_ip_banned(db, client_ip):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "IP banned due to suspicious activity"},
                    status_code=403,
                )
    except Exception:
        pass
    return await call_next(request)


async def _security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme != "http" or "debug" in str(request.url):
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    return response


limiter = Limiter(key_func=get_remote_address)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(app.state.settings)
    s = app.state.settings
    if s.effective_domain and s.panel_subdomain:
        import contextlib as _cl

        caddy = None
        from pit_panel.core.caddy import CaddyManager

        caddy = CaddyManager(s.caddy_admin_url)
        with _cl.suppress(Exception):
            await caddy.setup_panel_route(s.panel_subdomain, s.effective_domain, s.port)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = init_settings()

    app = FastAPI(
        title="pit-panel",
        version="0.1.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.limiter = limiter

    app.add_exception_handler(RateLimitExceeded, _make_ratelimit_handler())
    app.middleware("http")(_ip_ban_middleware)
    app.middleware("http")(_security_headers_middleware)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    router.state = app.state
    router.state.limiter = limiter

    from pit_panel.web.routes import (  # noqa: E402,F401
        apps,
        auth_routes,
        containers,
        dashboard,
        logs,
        security,
        settings,
        ssl,
        subdomains,
        system,
    )

    app.include_router(router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def _make_ratelimit_handler():
    from slowapi import _rate_limit_exceeded_handler

    async def handler(request: Request, exc: RateLimitExceeded):
        return await _rate_limit_exceeded_handler(request, exc)

    return handler

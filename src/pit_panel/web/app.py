"""FastAPI application factory with security middleware."""

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from pit_panel.config import Settings, init_settings
from pit_panel.db.session import get_sessionmaker
from pit_panel.security.ipban import is_ip_banned
from pit_panel.web.limiter import limiter


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from pit_panel.core.backup import scheduled_backup_loop
    from pit_panel.core.blocklist import daily_blocklist_import
    from pit_panel.core.caddy import ssl_auto_renew_loop
    from pit_panel.core.health import docker_health_monitor_loop

    tasks = [
        asyncio.create_task(daily_blocklist_import()),
        asyncio.create_task(ssl_auto_renew_loop()),
        asyncio.create_task(docker_health_monitor_loop()),
        asyncio.create_task(scheduled_backup_loop()),
    ]
    yield
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t


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


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = init_settings()

    app = FastAPI(
        title="pit-panel",
        version="0.1.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.limiter = limiter

    app.add_exception_handler(RateLimitExceeded, _make_ratelimit_handler())
    app.middleware("http")(_ip_ban_middleware)
    app.middleware("http")(_security_headers_middleware)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from pit_panel.web.routes import (
        apps_router,
        auth_router,
        containers_router,
        dashboard_router,
        debug_api_router,
        debug_router,
        logs_router,
        security_router,
        settings_router,
        ssl_router,
        subdomains_router,
        system_manage_router,
        system_router,
    )

    app.include_router(apps_router)
    app.include_router(auth_router)
    app.include_router(containers_router)
    app.include_router(dashboard_router)
    app.include_router(debug_router)
    app.include_router(debug_api_router)
    app.include_router(logs_router)
    app.include_router(security_router)
    app.include_router(settings_router)
    app.include_router(ssl_router)
    app.include_router(subdomains_router)
    app.include_router(system_router)
    app.include_router(system_manage_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def _make_ratelimit_handler():
    from slowapi import _rate_limit_exceeded_handler

    async def handler(request: Request, exc: RateLimitExceeded):
        return await _rate_limit_exceeded_handler(request, exc)

    return handler

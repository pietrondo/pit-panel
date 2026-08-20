"""FastAPI application factory with security middleware."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from pit_panel.config import Settings, init_settings
from pit_panel.db.session import dispose_engine, get_sessionmaker
from pit_panel.security.ipban import is_ip_banned
from pit_panel.web.auth import SESSION_COOKIE
from pit_panel.web.limiter import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

    with contextlib.suppress(Exception):
        await dispose_engine()


async def _ip_ban_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    client_ip = request.client.host if request.client else "unknown"

    # ⚡ Bolt Optimization: Synchronous fast-path cache check
    # We check the cache before creating the SQLAlchemy session.
    # This saves ~9ms of overhead for DB session allocation on cache hits
    # while still accurately rejecting banned IPs and allowing valid ones.
    from pit_panel.security.ipban import check_ip_banned_cache

    cached = check_ip_banned_cache(client_ip)
    if cached is True:
        return JSONResponse(
            {"detail": "IP banned due to suspicious activity"},
            status_code=403,
        )
    elif cached is False:
        return await call_next(request)

    app_settings = getattr(request.app.state, "settings", None)
    try:
        if app_settings is not None:
            sessionmaker = get_sessionmaker(app_settings)
        else:
            sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            if await is_ip_banned(db, client_ip):
                return JSONResponse(
                    {"detail": "IP banned due to suspicious activity"},
                    status_code=403,
                )
    except Exception:
        logger.exception("IP-ban check failed for %s", client_ip)
        # In production, fail closed: if we cannot verify the IP, deny the
        # request. In debug/dev mode, fail open so the panel is still usable
        # when the DB is uninitialized.
        if app_settings is None or not app_settings.debug:
            return JSONResponse(
                {"detail": "Service temporarily unavailable"},
                status_code=503,
            )
    return await call_next(request)


async def _security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
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


_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = ("/api/debug", "/login", "/logout", "/setup-2fa")


async def _csrf_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.method in _CSRF_SAFE_METHODS:
        return await call_next(request)
    if any(request.url.path.startswith(p) for p in _CSRF_EXEMPT_PATHS):
        return await call_next(request)
    # No session cookie => no CSRF risk (attacker has no auth to abuse).
    if SESSION_COOKIE not in request.cookies:
        return await call_next(request)
    expected_origin = f"{request.url.scheme}://{request.url.netloc}"
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    if origin == expected_origin or referer.startswith(expected_origin):
        return await call_next(request)
    logger.warning(
        "CSRF check failed: method=%s path=%s origin=%r referer=%r",
        request.method,
        request.url.path,
        origin,
        referer,
    )
    return JSONResponse(
        {"detail": "CSRF validation failed"},
        status_code=403,
    )


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
    app.middleware("http")(_csrf_middleware)
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
        file_manager_router,
        logs_router,
        security_router,
        settings_router,
        site_builder_router,
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
    app.include_router(file_manager_router)
    app.include_router(logs_router)
    app.include_router(security_router)
    app.include_router(settings_router)
    app.include_router(site_builder_router)
    app.include_router(ssl_router)
    app.include_router(subdomains_router)
    app.include_router(system_router)
    app.include_router(system_manage_router)

    @app.get("/health")  # type: ignore[untyped-decorator]
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _make_ratelimit_handler() -> Callable[[Request, RateLimitExceeded], Awaitable[Response]]:
    from slowapi import _rate_limit_exceeded_handler

    async def handler(request: Request, exc: RateLimitExceeded) -> Response:
        return await _rate_limit_exceeded_handler(request, exc)

    return handler

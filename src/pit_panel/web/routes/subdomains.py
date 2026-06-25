"""Subdomain CRUD routes with Caddy integration and audit logging."""

import contextlib
import re

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.db.models import AuditLog, Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render
from pit_panel.web.router import router


async def _log_audit(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None,
    details: dict[str, str] | None,
    request: Request,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(entry)
    await db.commit()


@router.get("/subdomains", response_class=HTMLResponse)
async def subdomains_list(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
    subdomains = result.scalars().all()

    return render("subdomains.html", user=user, subdomains=subdomains, error=None)


@router.post("/subdomains/add", response_class=HTMLResponse)
async def subdomain_add(
    request: Request,
    subdomain: str = Form(...),
    app_type: str = Form("none"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()

    safe_subdomain = subdomain.strip().lower().replace(" ", "-")
    if not safe_subdomain or not re.match(r"^[a-z0-9-]+$", safe_subdomain):
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        return render(
            "subdomains.html",
            user=user,
            subdomains=subdomains,
            error="Invalid subdomain name",
        )

    existing = await db.execute(
        select(Subdomain).where(
            Subdomain.subdomain == safe_subdomain,
            Subdomain.base_domain == settings.base_domain,
        )
    )
    if existing.scalar_one_or_none():
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        return render(
            "subdomains.html",
            user=user,
            subdomains=subdomains,
            error="Subdomain already exists",
        )

    sd = Subdomain(
        subdomain=safe_subdomain,
        base_domain=settings.base_domain,
        owner_user_id=user.id,
        app_type=app_type if app_type != "none" else None,
    )
    db.add(sd)
    await db.flush()

    if settings.base_domain:
        caddy = CaddyManager(settings.caddy_admin_url)
        with contextlib.suppress(Exception):
            await caddy.add_subdomain(safe_subdomain, settings.base_domain)

    await _log_audit(
        db,
        user.id,
        "subdomain_create",
        "subdomain",
        sd.id,
        {"subdomain": safe_subdomain},
        request,
    )
    await db.commit()

    return RedirectResponse("/subdomains", status_code=302)


@router.post("/subdomains/{sd_id}/delete", response_class=HTMLResponse)
async def subdomain_delete(
    request: Request,
    sd_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        if settings.base_domain:
            caddy = CaddyManager(settings.caddy_admin_url)
        with contextlib.suppress(Exception):
            await caddy.remove_subdomain(sd.subdomain, settings.base_domain)

        await _log_audit(
            db,
            user.id,
            "subdomain_delete",
            "subdomain",
            sd.id,
            {"subdomain": sd.subdomain},
            request,
        )
        await db.delete(sd)
        await db.commit()

    return RedirectResponse("/subdomains", status_code=302)

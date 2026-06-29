"""Settings and audit log routes."""

import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import AuditLog, SystemSettings
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50))
    audit_entries = result.scalars().all()

    return render(
        "settings.html",
        user=user,
        audit_entries=audit_entries,
        settings=get_settings(),
        config_saved=False,
        error=None,
    )


@router.post("/settings/update", response_class=HTMLResponse)
async def settings_update(
    request: Request,
    base_domain: str = Form(""),
    panel_subdomain: str = Form("panel"),
    abuseipdb_api_key: str = Form(""),
    sudo_password: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    new_base = base_domain.strip()
    new_panel = panel_subdomain.strip() or "panel"

    if new_base and not re.match(r"^[a-zA-Z0-9.-]+$", new_base):
        return HTMLResponse("Invalid base domain", status_code=400)
    if new_panel and not re.match(r"^[a-zA-Z0-9.-]+$", new_panel):
        return HTMLResponse("Invalid panel subdomain", status_code=400)
    new_host = "127.0.0.1" if new_base else "0.0.0.0"

    # Store in DB (no filesystem write needed)
    for key, val in [
        ("base_domain", new_base),
        ("panel_subdomain", new_panel),
        ("host", new_host),
        ("abuseipdb_api_key", abuseipdb_api_key.strip()),
        ("sudo_password", sudo_password),
    ]:
        result = await db.execute(select(SystemSettings).where(SystemSettings.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = {"v": val}
            row.updated_by = user.id
        else:
            db.add(SystemSettings(key=key, value={"v": val}, updated_by=user.id))
    await db.commit()

    # Update in-memory settings
    settings = get_settings()
    settings.base_domain = new_base
    settings.panel_subdomain = new_panel
    settings.host = new_host
    settings.abuseipdb_api_key = abuseipdb_api_key.strip()
    settings.sudo_password = sudo_password

    result = await db.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50))
    audit_entries = result.scalars().all()

    return render(
        "settings.html",
        user=user,
        audit_entries=audit_entries,
        settings=settings,
        config_saved=True,
        error=None,
    )


@router.get("/settings/audit", response_class=HTMLResponse)
async def audit_log(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100))
    entries = result.scalars().all()

    return render("audit.html", user=user, entries=entries)

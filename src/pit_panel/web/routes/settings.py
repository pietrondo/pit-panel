"""Settings and audit log routes."""

from pathlib import Path

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings, init_settings
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


def _write_config(settings):
    config_path = Path(settings.config_path)
    lines = config_path.read_text().splitlines() if config_path.exists() else []
    new_lines = []
    updated = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("base_domain =") and "base_domain" not in updated:
            new_lines.append(f'base_domain = "{settings.base_domain}"')
            updated.add("base_domain")
        elif stripped.startswith("panel_subdomain =") and "panel_subdomain" not in updated:
            new_lines.append(f'panel_subdomain = "{settings.panel_subdomain}"')
            updated.add("panel_subdomain")
        elif stripped.startswith("host =") and "host" not in updated:
            new_lines.append(f'host = "{settings.host}"')
            updated.add("host")
        else:
            new_lines.append(line)
    for key in ["base_domain", "panel_subdomain", "host"]:
        if key not in updated:
            val = getattr(settings, key)
            new_lines.append(f'{key} = "{val}"')
    config_path.write_text("\n".join(new_lines) + "\n")


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
        config_saved=False,
        error=None,
    )


@router.post("/settings/update", response_class=HTMLResponse)
async def settings_update(
    request: Request,
    base_domain: str = Form(""),
    panel_subdomain: str = Form("panel"),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    settings.base_domain = base_domain.strip()
    settings.panel_subdomain = panel_subdomain.strip() or "panel"

    # Auto-set host based on domain presence
    if settings.base_domain:
        settings.host = "127.0.0.1"
    else:
        settings.host = "0.0.0.0"

    try:
        _write_config(settings)
        init_settings(settings.config_path)  # reload
        config_saved = True
        error = None
    except Exception as e:
        config_saved = False
        error = str(e)

    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50)
    )
    audit_entries = result.scalars().all()

    return render(
        "settings.html",
        user=user,
        audit_entries=audit_entries,
        settings=get_settings(),
        config_saved=config_saved,
        error=error,
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

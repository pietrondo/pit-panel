"""Security overview: IP bans, login attempts, active sessions, firewall, fail2ban."""

import asyncio
import contextlib
import ipaddress
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.security import (
    _fail2ban_status,
    _firewall_status,
    ban_ip_address,
    unban_ip_address,
)
from pit_panel.db.models import LoginAttempt, MalwareScan, SystemSettings, User
from pit_panel.db.models import Session as DBSession
from pit_panel.db.session import get_db
from pit_panel.security.bug_analyzer import analyze_container_logs, analyze_system_logs
from pit_panel.security.ipban import get_banned_ips
from pit_panel.security.malware_scanner import (
    SCAN_DEFAULT_INTERVAL_HOURS,
    THREAT_CATEGORIES,
)
from pit_panel.web.auth import revoke_session
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

from .security_abuseipdb import router as abuseipdb_router
from .security_blocklist import router as blocklist_router
from .security_fail2ban import router as fail2ban_router
from .security_firewall import router as firewall_router
from .security_lynis import router as lynis_router
from .security_malware import router as malware_router

router = APIRouter()
router.include_router(malware_router)
router.include_router(firewall_router)
router.include_router(fail2ban_router)
router.include_router(blocklist_router)
router.include_router(abuseipdb_router)
router.include_router(lynis_router)


async def _rollback_after_db_panel_error(db: AsyncSession) -> None:
    with contextlib.suppress(Exception):
        await db.rollback()


async def _load_bans(db: AsyncSession) -> list[Any]:
    try:
        return await get_banned_ips(db)
    except Exception:
        await _rollback_after_db_panel_error(db)
        return []


async def _load_attempts(db: AsyncSession) -> list[Any]:
    try:
        result = await db.execute(
            select(LoginAttempt).order_by(LoginAttempt.attempted_at.desc()).limit(50)
        )
        return list(result.scalars().all())
    except Exception:
        await _rollback_after_db_panel_error(db)
        return []


async def _load_active_sessions(db: AsyncSession) -> list[dict[str, Any]]:
    try:
        result = await db.execute(
            select(DBSession, User.username)
            .join(User, DBSession.user_id == User.id)
            .order_by(DBSession.created_at.desc())
        )
        return [
            {
                "id": sess.id,
                "username": uname,
                "ip": sess.ip,
                "created": sess.created_at,
            }
            for sess, uname in result
        ]
    except Exception:
        await _rollback_after_db_panel_error(db)
        return []


async def _load_scan_history(db: AsyncSession) -> list[Any]:
    try:
        result = await db.execute(
            select(MalwareScan).order_by(MalwareScan.started_at.desc()).limit(5)
        )
        return list(result.scalars().all())
    except Exception:
        await _rollback_after_db_panel_error(db)
        return []


async def _load_scan_interval_hours(db: AsyncSession) -> int:
    try:
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == "scan_interval_hours")
        )
        row = result.scalar_one_or_none()
        if row:
            return int(row.value.get("hours", SCAN_DEFAULT_INTERVAL_HOURS))
    except Exception:
        await _rollback_after_db_panel_error(db)
    return SCAN_DEFAULT_INTERVAL_HOURS


async def _render_security_page(request: Request, db: AsyncSession, user: User, **kwargs):
    async def _db_group():
        bans = await _load_bans(db)
        attempts = await _load_attempts(db)
        active_sessions = await _load_active_sessions(db)
        scan_history = await _load_scan_history(db)
        scan_interval_hours = await _load_scan_interval_hours(db)
        return bans, attempts, active_sessions, scan_history, scan_interval_hours

    (
        (bans, attempts, active_sessions, scan_history, scan_interval_hours),
        (fw, f2b),
    ) = await asyncio.gather(_db_group(), asyncio.gather(_firewall_status(), _fail2ban_status()))

    settings = get_settings()
    abuseipdb_key = getattr(settings, "abuseipdb_api_key", "")

    ctx = {
        "user": user,
        "bans": bans,
        "attempts": attempts,
        "sessions": active_sessions,
        "unban_result": None,
        "firewall": fw,
        "fail2ban": f2b,
        "abuseipdb_key": abuseipdb_key != "",
        "ban_result": None,
        "scan_history": scan_history,
        "scan_interval_hours": scan_interval_hours,
        "threat_categories": THREAT_CATEGORIES,
    }
    ctx.update(kwargs)

    return render("security.html", **ctx)


@router.get("/security", response_class=HTMLResponse)
async def security_overview(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    return await _render_security_page(request, db, user)


@router.post("/security/unban", response_class=HTMLResponse)
async def security_unban(
    request: Request,
    ip: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Unban a previously banned IP address."""
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = None
    if ip:
        try:
            ipaddress.ip_network(ip, strict=False)
        except ValueError:
            return HTMLResponse(
                "<span class='text-red-500 text-xs'>Invalid IP address</span>", status_code=400
            )
        ok = await unban_ip_address(db, ip, user.id)
        result = {"ip": ip, "success": ok}

    return await _render_security_page(request, db, user, unban_result=result)


@router.post("/security/revoke-session", response_class=HTMLResponse)
async def security_revoke_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Revoke an active user session."""
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    session_id = int(form.get("session_id", 0))
    if session_id:
        await revoke_session(db, session_id)

    return RedirectResponse("/security", status_code=302)


@router.post("/security/ban-ip", response_class=HTMLResponse)
async def security_ban_ip(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Ban an IP address manually."""
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    ip = str(form.get("ip", "")).strip()
    reason = str(form.get("reason", "manual")).strip() or "manual"
    duration = int(form.get("duration", 60))

    result = None
    if ip:
        try:
            ipaddress.ip_network(ip, strict=False)
        except ValueError:
            return HTMLResponse(
                "<span class='text-red-500 text-xs'>Invalid IP address</span>", status_code=400
            )
        ok = await ban_ip_address(db, ip, reason, duration)
        result = {"ip": ip, "ok": ok}

    return await _render_security_page(request, db, user, ban_result=result)


@router.get("/security/bugs", response_class=HTMLResponse)
async def security_bugs(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    container_bugs = await analyze_container_logs()
    system_bugs = await analyze_system_logs()

    html = '<div class="space-y-4">'

    if not container_bugs and not system_bugs:
        return HTMLResponse(
            '<div class="text-sm text-green-600 p-4 bg-green-50 '
            "dark:bg-green-900/10 rounded border border-green-200 "
            'dark:border-green-800">✅ Nessun errore o bug rilevato nei log.</div>'
        )

    if container_bugs:
        html += (
            '<h3 class="text-sm font-semibold text-gray-900 '
            'dark:text-white mt-2">🐳 Errori App Containerizzate</h3>'
        )
        for app in container_bugs:
            html += (
                '<div class="p-3 bg-red-50 dark:bg-red-900/10 border '
                'border-red-200 dark:border-red-800 rounded">\n'
                '  <div class="flex justify-between items-center mb-2">\n'
                '    <span class="font-mono text-sm font-bold text-red-700 '
                f'dark:text-red-400">{app["container"]}</span>\n'
                '    <span class="text-xs bg-red-200 text-red-800 dark:bg-red-900 '
                f'dark:text-red-300 px-2 py-0.5 rounded-full">{app["count"]} errori</span>\n'
                "  </div>\n"
                '  <ul class="list-disc pl-5 text-xs text-red-600 dark:text-red-400 space-y-1">\n'
            )
            for err in app["errors"]:
                html += f'    <li class="break-all">{__import__("html").escape(err)}</li>\n'
            html += "  </ul></div>\n"

    if system_bugs:
        html += (
            '<h3 class="text-sm font-semibold text-gray-900 '
            'dark:text-white mt-4">⚙️ Errori di Sistema (Pit Panel)</h3>'
        )
        html += (
            '<div class="p-3 bg-orange-50 dark:bg-orange-900/10 border '
            'border-orange-200 dark:border-orange-800 rounded">\n'
            '<ul class="list-disc pl-5 text-xs text-orange-700 dark:text-orange-400 space-y-1">\n'
        )
        for err in system_bugs:
            html += f'  <li class="break-all">{__import__("html").escape(err)}</li>\n'
        html += "</ul></div>\n"

    html += "</div>"
    return HTMLResponse(html)

"""Security overview: IP bans, login attempts, active sessions, firewall, fail2ban."""

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
from pit_panel.security.ipban import get_banned_ips
from pit_panel.security.malware_scanner import (
    SCAN_DEFAULT_INTERVAL_HOURS,
    THREAT_CATEGORIES,
    MalwareScanner,
)
from pit_panel.web.auth import revoke_session
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()


async def _abuseipdb_check(ip: str, api_key: str) -> dict:
    import http.client
    import json

    try:
        ip = ip.replace("\r", "").replace("\n", "")
        api_key = api_key.replace("\r", "").replace("\n", "")
        conn = http.client.HTTPSConnection("api.abuseipdb.com", timeout=10)
        headers = {"Key": api_key, "Accept": "application/json"}
        conn.request("GET", f"/api/v2/check?ipAddress={ip}&maxAgeInDays=90", headers=headers)
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            score = data.get("data", {}).get("abuseConfidenceScore", 0)
            return {
                "ip": ip,
                "score": score,
                "reports": data.get("data", {}).get("totalReports", 0),
            }
        return {"ip": ip, "error": f"HTTP {resp.status}"}
    except Exception as e:
        return {"ip": ip, "error": str(e)}


async def _abuseipdb_blacklist(api_key: str, limit: int = 20) -> list[dict]:
    import http.client
    import json

    try:
        conn = http.client.HTTPSConnection("api.abuseipdb.com", timeout=15)
        headers = {"Key": api_key, "Accept": "application/json"}
        conn.request(
            "GET",
            f"/api/v2/blacklist?confidenceMinimum=90&limit={limit}",
            headers=headers,
        )
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            entries = data.get("data", [])
            return [
                {
                    "ip": e.get("ipAddress", ""),
                    "score": e.get("abuseConfidenceScore", 0),
                    "reports": e.get("totalReports", 0),
                    "last": e.get("lastReportedAt", ""),
                }
                for e in entries
            ]
        return []
    except Exception:
        return []


async def _render_security_page(request: Request, db: AsyncSession, user: User, **kwargs):
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

    fw = await _firewall_status()
    f2b = await _fail2ban_status()

    try:
        scan_result = await db.execute(
            select(MalwareScan).order_by(MalwareScan.started_at.desc()).limit(5)
        )
        scan_history = scan_result.scalars().all()
    except Exception:
        from pit_panel.db.models import Base
        from pit_panel.db.session import get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        scan_history = []

    settings = get_settings()
    abuseipdb_key = getattr(settings, "abuseipdb_api_key", "")

    scan_interval_hours = SCAN_DEFAULT_INTERVAL_HOURS
    try:
        sr = await db.execute(
            select(SystemSettings).where(SystemSettings.key == "scan_interval_hours")
        )
        row = sr.scalar_one_or_none()
        if row:
            scan_interval_hours = int(row.value.get("hours", SCAN_DEFAULT_INTERVAL_HOURS))
    except Exception:
        pass

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
        ok = await ban_ip_address(db, ip, reason, duration)
        result = {"ip": ip, "ok": ok}

    return await _render_security_page(request, db, user, ban_result=result)


@router.post("/security/malware/scan", response_class=HTMLResponse)
async def security_malware_scan(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized")

    from datetime import datetime

    settings = get_settings()
    scanner = MalwareScanner(settings.apps_dir)
    clamav = await scanner.check_docker_clamav()

    if not clamav:
        try:
            msg = await scanner.pull_clamav()
        except Exception:
            msg = "Failed to pull ClamAV image"
        return HTMLResponse(
            f'<p class="text-amber-600">ClamAV Docker image not found. Pulling...<br>{msg}</p>'
            f'<button class="btn-primary mt-2" hx-post="/security/malware/scan" '
            f'hx-target="closest div" hx-swap="outerHTML">Retry</button>'
        )

    scan = MalwareScan(target="all", scan_type="full", status="running")
    db.add(scan)
    await db.commit()

    try:
        results = await scanner.scan_all()
        total_infected = sum(r.get("infected_total", 0) for r in results)
        total_scanned = sum(r.get("scanned_total", 0) for r in results)
        scan.status = "completed"
        scan.infected_count = total_infected
        scan.scanned_count = total_scanned
        scan.details = {"apps": results}
    except Exception as e:
        scan.status = "failed"
        scan.details = {"error": str(e)}

    scan.completed_at = datetime.utcnow()
    await db.commit()

    return await security_overview(request, db)


@router.post("/security/malware/scan-full", response_class=HTMLResponse)
async def security_malware_scan_full(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized")
    from datetime import datetime

    scanner = MalwareScanner(get_settings().apps_dir)
    scan = MalwareScan(target="system (full)", scan_type="full", status="running")
    db.add(scan)
    await db.commit()
    try:
        result = await scanner.scan_path("/")
        scan.status = "completed"
        scan.infected_count = result["infected_total"]
        scan.scanned_count = result["scanned_total"]
        scan.details = {"apps": [result]}
    except Exception as e:
        scan.status = "failed"
        scan.details = {"error": str(e)}
    scan.completed_at = datetime.utcnow()
    await db.commit()
    return await security_overview(request, db)


@router.post("/security/malware/set-interval", response_class=HTMLResponse)
async def security_malware_set_interval(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized")
    form = await request.form()
    hours = int(form.get("hours", SCAN_DEFAULT_INTERVAL_HOURS))
    hours = max(1, min(168, hours))
    sr = await db.execute(select(SystemSettings).where(SystemSettings.key == "scan_interval_hours"))
    row = sr.scalar_one_or_none()
    if row:
        row.value = {"hours": hours}
    else:
        db.add(SystemSettings(key="scan_interval_hours", value={"hours": hours}))
    await db.commit()
    return HTMLResponse(f'<span class="text-green-600">Scan interval set to {hours}h</span>')


@router.post("/security/malware/update-defs", response_class=HTMLResponse)
async def security_malware_update_defs(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized")

    scanner = MalwareScanner(get_settings().apps_dir)
    result = await scanner.update_definitions()
    if result.get("ok"):
        return HTMLResponse(
            f'<span class="text-green-600">Definitions updated: '
            f"{result.get('output', '')[:200]}</span>"
        )
    return HTMLResponse(
        f'<span class="text-red-600">Update failed: {result.get("error", "unknown")[:200]}</span>'
    )

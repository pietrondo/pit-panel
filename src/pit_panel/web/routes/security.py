"""Security overview: IP bans, login attempts, active sessions, firewall, fail2ban."""

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.blocklist import BLOCKLIST_SOURCES, fetch_blocklist
from pit_panel.core.security import (
    JAIL_DEFAULTS,
    _fail2ban_status,
    _firewall_status,
    _run_cmd,
    ban_ip_address,
    unban_ip_address,
)
from pit_panel.db.models import LoginAttempt, User
from pit_panel.db.models import Session as DBSession
from pit_panel.db.session import get_db
from pit_panel.security.ipban import ban_ip, get_banned_ips
from pit_panel.web.auth import revoke_session
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render
from pit_panel.web.router import router


async def _abuseipdb_check(ip: str, api_key: str) -> dict:
    import http.client
    import json

    try:
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


async def _get_security_context(db: AsyncSession) -> dict:
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

    settings = get_settings()
    abuseipdb_key = getattr(settings, "abuseipdb_api_key", "") != ""

    return {
        "bans": bans,
        "attempts": attempts,
        "sessions": active_sessions,
        "firewall": fw,
        "fail2ban": f2b,
        "abuseipdb_key": abuseipdb_key,
    }


@router.get("/security", response_class=HTMLResponse)
async def security_overview(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    ctx = await _get_security_context(db)

    return render(
        "security.html",
        user=user,
        bans=ctx["bans"],
        attempts=ctx["attempts"],
        sessions=ctx["sessions"],
        unban_result=None,
        firewall=ctx["firewall"],
        fail2ban=ctx["fail2ban"],
        abuseipdb_key=ctx["abuseipdb_key"],
        ban_result=None,
    )


@router.post("/security/unban", response_class=HTMLResponse)
async def security_unban(
    request: Request,
    ip: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = None
    if ip:
        ok = await unban_ip_address(db, ip, user.id)
        result = {"ip": ip, "success": ok}

    ctx = await _get_security_context(db)

    return render(
        "security.html",
        user=user,
        bans=ctx["bans"],
        attempts=ctx["attempts"],
        sessions=ctx["sessions"],
        unban_result=result,
        firewall=ctx["firewall"],
        fail2ban=ctx["fail2ban"],
        abuseipdb_key=ctx["abuseipdb_key"],
        ban_result=None,
    )


@router.post("/security/revoke-session", response_class=HTMLResponse)
async def security_revoke_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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

    ctx = await _get_security_context(db)

    return render(
        "security.html",
        user=user,
        bans=ctx["bans"],
        attempts=ctx["attempts"],
        sessions=ctx["sessions"],
        unban_result=None,
        firewall=ctx["firewall"],
        fail2ban=ctx["fail2ban"],
        abuseipdb_key=ctx["abuseipdb_key"],
        ban_result=result,
    )


@router.post("/security/abuseipdb-check")
async def security_abuseipdb_check(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    ip = str(form.get("ip", "")).strip()
    api_key = str(form.get("api_key", "")).strip()
    if not ip or not api_key:
        return HTMLResponse("<p class='text-red-500'>IP and API key required</p>")

    result = await _abuseipdb_check(ip, api_key)
    if "error" in result:
        return HTMLResponse(f"<p class='text-red-500'>Error checking {ip}: {result['error']}</p>")
    return HTMLResponse(
        f"<div class='text-sm'>"
        f"<span class='font-mono'>{result['ip']}</span>: "
        f"<span class='font-bold {'text-red-500' if result['score'] > 50 else 'text-green-500'}'>"
        f"Score {result['score']}/100</span> "
        f"({result['reports']} reports)"
        f"</div>"
    )


@router.get("/security/abuseipdb-blacklist")
async def security_abuseipdb_blacklist(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("<p class='text-red-500'>Unauthorized</p>")

    settings = get_settings()
    api_key = settings.abuseipdb_api_key
    if not api_key:
        return HTMLResponse("<p class='text-yellow-500'>Set abuseipdb_api_key in config.toml</p>")

    entries = await _abuseipdb_blacklist(api_key)
    if not entries:
        return HTMLResponse("<p class='text-gray-500'>No entries or API error</p>")

    rows = []
    for e in entries:
        rows.append(
            f"<tr>"
            f"<td class='px-3 py-1 font-mono text-xs'>{e['ip']}</td>"
            f"<td class='px-3 py-1'><span class='text-xs font-bold "
            f"{'text-red-500' if e['score'] > 70 else 'text-yellow-500'}'>"
            f"{e['score']}/100</span></td>"
            f"<td class='px-3 py-1 text-xs text-gray-500'>{e['reports']}</td>"
            f"<td class='px-3 py-1'>"
            f"<form method='POST' action='/security/ban-ip' class='inline'>"
            f"<input type='hidden' name='ip' value='{e['ip']}'>"
            f"<input type='hidden' name='reason' value='abuseipdb'>"
            f"<input type='hidden' name='duration' value='1440'>"
            f"<button type='submit' class='btn-ghost text-xs text-red-600'>Ban</button>"
            f"</form>"
            f"</td>"
            f"</tr>"
        )
    return HTMLResponse("<table class='w-full'>" + "".join(rows) + "</table>")


@router.get("/security/blocklist")
async def security_blocklist_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    html = "<div class='space-y-2'>"
    for key, info in BLOCKLIST_SOURCES.items():
        html += (
            f"<div class='flex items-center justify-between p-2 "
            f"bg-gray-50 dark:bg-gray-800 rounded'>"
            f"<div>"
            f"<span class='font-medium text-sm'>{info['name']}</span>"
            f"<p class='text-xs text-gray-500'>{info['desc']}</p>"
            f"</div>"
            f"<button class='btn-ghost text-xs' "
            f"hx-post='/security/blocklist/import' "
            f'hx-vals=\'{{"source":"{key}"}}\' '
            f"hx-target='#blocklist-result' "
            f"hx-swap='innerHTML'>Import</button>"
            f"</div>"
        )
    html += "</div><div id='blocklist-result' class='mt-2 text-xs'></div>"
    return HTMLResponse(html)


@router.post("/security/blocklist/import")
async def security_blocklist_import(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("<p class='text-red-500'>Unauthorized</p>")

    form = await request.form()
    source = str(form.get("source", ""))
    info = BLOCKLIST_SOURCES.get(source)
    if not info:
        return HTMLResponse("<p class='text-red-500'>Invalid source</p>")

    ips = await fetch_blocklist(info["url"])
    if not ips:
        return HTMLResponse("<p class='text-yellow-500'>No IPs found</p>")

    count = 0
    for ip in ips:
        try:
            ok = await ban_ip(db, ip, f"blocklist:{source}", 10080)
            if ok:
                count += 1
        except Exception:
            pass

    return HTMLResponse(
        f"<p class='text-green-500'>Imported {count}/{len(ips)} IPs from {info['name']}</p>"
    )


@router.post("/security/fail2ban/enable")
async def security_fail2ban_enable(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("<p class='text-red-500'>Unauthorized</p>")

    form = await request.form()
    jail = str(form.get("jail", ""))
    if jail not in JAIL_DEFAULTS:
        return HTMLResponse(f"<p class='text-red-500'>Invalid jail: {jail}</p>")

    cfg = JAIL_DEFAULTS[jail]
    lines = [f"[{jail}]", "enabled = true"]
    for k, v in cfg.items():
        lines.append(f"{k} = {v}")

    _run_cmd(
        ["sudo", "-n", "tee", "/etc/fail2ban/jail.local"],
        timeout=10,
        input="\n".join(lines) + "\n",
    )
    _run_cmd(["sudo", "-n", "systemctl", "restart", "fail2ban"])
    return HTMLResponse(f"<p class='text-green-500'>Jail {jail} enabled</p>")


@router.get("/security/fail2ban/jails")
async def security_fail2ban_jails_html(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("<p class='text-red-500'>Unauthorized</p>")

    f2b = await _fail2ban_status()
    rows = []
    for jail in f2b.get("jails", []):
        rows.append(
            f"<span class='px-2 py-1 text-xs font-mono "
            f"bg-green-100 dark:bg-green-900/30 text-green-700 "
            f"dark:text-green-400 rounded'>{jail}</span>"
        )

    if not rows:
        return HTMLResponse("<p class='text-sm text-gray-500'>No active jails</p>")

    return HTMLResponse("<div class='flex flex-wrap gap-2'>" + "".join(rows) + "</div>")

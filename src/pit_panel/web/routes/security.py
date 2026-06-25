"""Security overview: IP bans, login attempts, active sessions, firewall, fail2ban."""

import subprocess

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import LoginAttempt, User
from pit_panel.db.models import Session as DBSession
from pit_panel.db.session import get_db
from pit_panel.security.ipban import ban_ip, get_banned_ips, unban_ip
from pit_panel.web.auth import revoke_session
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render
from pit_panel.web.router import router


def _run_cmd(cmd: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception:
        return "unavailable"


async def _firewall_status() -> dict:
    ufw = _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
    active = "Status: active" in ufw
    rules = []
    for line in ufw.split("\n"):
        if line.strip() and line.strip() != "Status: active":
            rules.append(line.strip())
    return {"active": active, "rules": rules[:20]}


async def _fail2ban_status() -> dict:
    status = _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
    jails = []
    active = "|- Number of jail:" in status
    for line in status.split("\n"):
        line = line.strip()
        if line.startswith("- ") and "Jail list:" not in line:
            jails.append(line.lstrip("- "))
    return {"active": active, "jails": jails}


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


@router.get("/security", response_class=HTMLResponse)
async def security_overview(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

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
    abuseipdb_key = getattr(settings, "abuseipdb_api_key", "")

    return render(
        "security.html",
        user=user,
        bans=bans,
        attempts=attempts,
        sessions=active_sessions,
        unban_result=None,
        firewall=fw,
        fail2ban=f2b,
        abuseipdb_key=abuseipdb_key != "",
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
        ok = await unban_ip(db, ip, user.id)
        result = {"ip": ip, "success": ok}

    bans = await get_banned_ips(db)
    attempts_result = await db.execute(
        select(LoginAttempt).order_by(LoginAttempt.attempted_at.desc()).limit(50)
    )
    attempts = attempts_result.scalars().all()

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

    return render(
        "security.html",
        user=user,
        bans=bans,
        attempts=attempts,
        sessions=active_sessions,
        unban_result=result,
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
        ok = await ban_ip(db, ip, reason, duration)
        result = {"ip": ip, "ok": ok}

    bans = await get_banned_ips(db)
    attempts_result = await db.execute(
        select(LoginAttempt).order_by(LoginAttempt.attempted_at.desc()).limit(50)
    )
    attempts = attempts_result.scalars().all()

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

    return render(
        "security.html",
        user=user,
        bans=bans,
        attempts=attempts,
        sessions=active_sessions,
        unban_result=None,
        firewall=fw,
        fail2ban=f2b,
        abuseipdb_key=False,
        ban_result=result,
    )


@router.post("/security/abuseipdb-check")
async def security_abuseipdb_check(
    request: Request, db: AsyncSession = Depends(get_db)
):
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
        return HTMLResponse(
            f"<p class='text-red-500'>Error checking {ip}: {result['error']}</p>"
        )
    return HTMLResponse(
        f"<div class='text-sm'>"
        f"<span class='font-mono'>{result['ip']}</span>: "
        f"<span class='font-bold {'text-red-500' if result['score'] > 50 else 'text-green-500'}'>"
        f"Score {result['score']}/100</span> "
        f"({result['reports']} reports)"
        f"</div>"
    )

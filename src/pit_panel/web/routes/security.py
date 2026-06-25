"""Security overview: IP bans, login attempts, active sessions, firewall, fail2ban."""

import subprocess

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.blocklist import BLOCKLIST_SOURCES, fetch_blocklist
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
    if "not found" in ufw.lower() or "command not found" in ufw.lower():
        install = _run_cmd(
            ["sudo", "-n", "apt-get", "install", "-y", "ufw"], timeout=60
        )
        if "Setting up ufw" in install or "ufw is already" in install:
            _run_cmd(["sudo", "-n", "ufw", "--force", "enable"])
            for port in ["22/tcp", "80/tcp", "443/tcp", "8080/tcp"]:
                _run_cmd(["sudo", "-n", "ufw", "allow", port])
            ufw = _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
    active = "Status: active" in ufw
    if not active and "Status: inactive" in ufw:
        _run_cmd(["sudo", "-n", "ufw", "--force", "enable"])
        for port in ["22/tcp", "80/tcp", "443/tcp", "8080/tcp"]:
            _run_cmd(["sudo", "-n", "ufw", "allow", port])
        ufw = _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
        active = "Status: active" in ufw
    rules = []
    for line in ufw.split("\n"):
        stripped = line.strip()
        if stripped and stripped != "Status: active" and "sudo:" not in stripped:
            rules.append(stripped)
    return {"active": active, "rules": rules[:20]}


async def _fail2ban_status() -> dict:
    status = _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
    if "not found" in status.lower() or "command not found" in status.lower():
        install = _run_cmd(
            ["sudo", "-n", "apt-get", "install", "-y", "fail2ban"], timeout=60
        )
        if "Setting up fail2ban" in install or "fail2ban is already" in install:
            _ensure_fail2ban_jails()
            status = _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
    jails = []
    active = "|- Number of jail:" in status
    if "sudo:" in status and "|- Number of jail:" not in status:
        return {"active": False, "jails": []}
    for line in status.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- ") and "Jail list:" not in stripped:
            jails.append(stripped.lstrip("- "))
    if active and not jails:
        _ensure_fail2ban_jails()
        status = _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
        for line in status.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- ") and "Jail list:" not in stripped:
                jails.append(stripped.lstrip("- "))
    return {"active": active, "jails": jails}


JAIL_DEFAULTS = {
    "sshd": {
        "port": "ssh",
        "filter": "sshd",
        "logpath": "/var/log/auth.log",
        "maxretry": "5",
        "bantime": "3600",
    },
}


def _ensure_fail2ban_jails():
    lines = []
    for jail, cfg in JAIL_DEFAULTS.items():
        lines.append(f"[{jail}]")
        for k, v in cfg.items():
            lines.append(f"{k} = {v}")
        lines.append("")
    content = "\n".join(lines)
    _run_cmd(
        ["sudo", "-n", "tee", "/etc/fail2ban/jail.local"],
        timeout=10,
        input=content,
    )
    _run_cmd(["sudo", "-n", "systemctl", "restart", "fail2ban"])


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


@router.get("/security/abuseipdb-blacklist")
async def security_abuseipdb_blacklist(
    request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("<p class='text-red-500'>Unauthorized</p>")

    settings = get_settings()
    api_key = settings.abuseipdb_api_key
    if not api_key:
        return HTMLResponse(
            "<p class='text-yellow-500'>Set abuseipdb_api_key in config.toml</p>"
        )

    entries = await _abuseipdb_blacklist(api_key)
    if not entries:
        return HTMLResponse(
            "<p class='text-gray-500'>No entries or API error</p>"
        )

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
    return HTMLResponse(
        "<table class='w-full'>"
        + "".join(rows)
        + "</table>"
    )


@router.get("/security/blocklist")
async def security_blocklist_page(
    request: Request, db: AsyncSession = Depends(get_db)
):
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
            f"hx-vals='{{\"source\":\"{key}\"}}' "
            f"hx-target='#blocklist-result' "
            f"hx-swap='innerHTML'>Import</button>"
            f"</div>"
        )
    html += "</div><div id='blocklist-result' class='mt-2 text-xs'></div>"
    return HTMLResponse(html)


@router.post("/security/blocklist/import")
async def security_blocklist_import(
    request: Request, db: AsyncSession = Depends(get_db)
):
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
        f"<p class='text-green-500'>Imported {count}/{len(ips)} IPs "
        f"from {info['name']}</p>"
    )

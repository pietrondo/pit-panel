"""Security overview: IP bans, login attempts, active sessions, firewall, fail2ban."""

import contextlib
import ipaddress
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.blocklist import BLOCKLIST_SOURCES, fetch_blocklist
from pit_panel.core.security import (
    _add_ufw_rule,
    _delete_ufw_rule,
    _detect_ssh_port,
    _disable_ufw,
    _enable_ufw,
    _fail2ban_jail_banned,
    _fail2ban_status,
    _fail2ban_unban,
    _firewall_status,
    _get_client_ip,
    _get_jail_config,
    _save_jail_config,
    ban_ip_address,
    run_lynis_audit,
    unban_ip_address,
)
from pit_panel.db.models import LoginAttempt, MalwareScan, SystemSettings, User
from pit_panel.db.models import Session as DBSession
from pit_panel.db.session import get_db
from pit_panel.security.bug_analyzer import analyze_container_logs, analyze_system_logs
from pit_panel.security.ipban import ban_ips_bulk, get_banned_ips
from pit_panel.security.malware_scanner import (
    SCAN_DEFAULT_INTERVAL_HOURS,
    THREAT_CATEGORIES,
    MalwareScanner,
    get_host_memory_gb,
)
from pit_panel.web.auth import revoke_session
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()


async def _abuseipdb_check(ip: str, api_key: str) -> dict[str, Any]:
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


async def _abuseipdb_blacklist(api_key: str, limit: int = 20) -> list[dict[str, Any]]:
    import http.client
    import json

    try:
        api_key = api_key.replace("\r", "").replace("\n", "")
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
    bans = await _load_bans(db)
    attempts = await _load_attempts(db)
    active_sessions = await _load_active_sessions(db)

    fw = await _firewall_status()
    f2b = await _fail2ban_status()
    scan_history = await _load_scan_history(db)

    settings = get_settings()
    abuseipdb_key = getattr(settings, "abuseipdb_api_key", "")
    scan_interval_hours = await _load_scan_interval_hours(db)

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


async def run_malware_scan_bg(scan_id: int, target: str, scan_path: str = None) -> None:
    from datetime import datetime

    from pit_panel.db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        scan = await db.get(MalwareScan, scan_id)
        if not scan:
            return

        try:
            settings = get_settings()
            scanner = MalwareScanner(settings.apps_dir)
            if target == "all":
                results = await scanner.scan_all()
                total_infected = sum(r.get("infected_total", 0) for r in results)
                total_scanned = sum(r.get("scanned_total", 0) for r in results)
                scan.status = "completed"
                scan.infected_count = total_infected
                scan.scanned_count = total_scanned
                scan.details = {"apps": results}
            else:
                result = await scanner.scan_path(scan_path or "/")
                scan.status = "completed"
                scan.infected_count = result.get("infected_total", 0)
                scan.scanned_count = result.get("scanned_total", 0)
                scan.details = {"apps": [result]}
        except Exception as e:
            scan.status = "failed"
            scan.details = {"error": str(e)}

        scan.completed_at = datetime.utcnow()
        await db.commit()


@router.post("/security/malware/scan", response_class=HTMLResponse)
async def security_malware_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized")

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

    background_tasks.add_task(run_malware_scan_bg, scan.id, "all")

    return HTMLResponse("", headers={"HX-Refresh": "true"})


@router.post("/security/malware/scan-full", response_class=HTMLResponse)
async def security_malware_scan_full(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized")

    scan = MalwareScan(target="system (full)", scan_type="full", status="running")
    db.add(scan)
    await db.commit()

    background_tasks.add_task(run_malware_scan_bg, scan.id, "system", "/")

    return HTMLResponse("", headers={"HX-Refresh": "true"})


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


@router.get("/security/malware/clamav-status", response_class=HTMLResponse)
async def security_clamav_status(request: Request, db: AsyncSession = Depends(get_db)):
    import subprocess

    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", "name=clamav", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        status = r.stdout.strip()
        if status:
            return HTMLResponse('<span class="text-green-600">🛡️ ClamAV: Up</span>')
        return HTMLResponse('<span class="text-yellow-600">🛡️ ClamAV: Not running</span>')
    except Exception:
        return HTMLResponse('<span class="text-gray-400">🛡️ ClamAV: N/A</span>')


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


@router.get("/security/blocklist", response_class=HTMLResponse)
async def security_blocklist_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

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


@router.post("/security/blocklist/import", response_class=HTMLResponse)
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

    count = await ban_ips_bulk(db, ips, f"blocklist:{source}", 10080)

    return HTMLResponse(
        f"<p class='text-green-500'>Imported {count}/{len(ips)} IPs from {info['name']}</p>"
    )


@router.post("/security/fail2ban/enable", response_class=HTMLResponse)
async def security_fail2ban_enable(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    import subprocess

    form = await request.form()
    jail = str(form.get("jail", ""))
    import re

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse(
            '<span class="text-red-600 text-xs">❌ Invalid jail name</span>', status_code=400
        )
    jail_escaped = __import__("html").escape(jail)

    try:
        r = subprocess.run(
            ["sudo", "-n", "fail2ban-client", "start", jail],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            return HTMLResponse(
                f'<span class="text-green-600 text-xs">✅ {jail_escaped} enabled</span>'
            )
        return HTMLResponse(
            f'<span class="text-red-600 text-xs">❌ {jail_escaped}: {r.stderr.strip()[:100]}</span>'
        )
    except FileNotFoundError:
        return HTMLResponse(
            '<span class="text-yellow-600 text-xs">fail2ban-client not found</span>'
        )
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-600 text-xs">Error: {e}</span>')


@router.get("/security/fail2ban/jail/{jail}", response_class=HTMLResponse)
async def security_fail2ban_jail(request: Request, jail: str, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    import re

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse(
            '<span class="text-red-600 text-xs">❌ Invalid jail name</span>', status_code=400
        )

    import html
    import re

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse(
            '<div class="text-xs text-red-500">Invalid jail name</div>', status_code=400
        )

    jailed = await _fail2ban_jail_banned(jail)
    jail_e = html.escape(jail)

    if not jailed:
        msg = f"Nessun IP bloccato in <strong>{jail_e}</strong>"
        return HTMLResponse(f'<div class="text-xs text-gray-500">{msg}</div>')

    rows = "".join(
        '<div class="flex items-center justify-between py-1.5 px-3 '
        'bg-gray-50 dark:bg-gray-800/50 rounded-lg">'
        f'<span class="font-mono text-xs">{e["ip"]}</span>'
        f'<button class="btn-ghost text-xs text-green-600" '
        f'hx-post="/security/fail2ban/unban" '
        f'hx-vals=\'{{"jail":"{jail_e}","ip":"{e["ip"]}"}}\' '
        f'hx-target="closest div" '
        f'hx-swap="outerHTML">Sblocca</button>'
        f"</div>"
        for e in jailed
    )
    count_msg = f"IP bloccati in <strong>{jail_e}</strong>: {len(jailed)}"
    return HTMLResponse(
        f'<div class="space-y-2"><p class="text-xs text-gray-500 mb-2">{count_msg}</p>{rows}</div>'
    )


@router.post("/security/fail2ban/unban", response_class=HTMLResponse)
async def security_fail2ban_unban(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    form = await request.form()
    jail = str(form.get("jail", ""))
    ip = str(form.get("ip", ""))
    import ipaddress
    import re

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse(
            '<div class="text-xs text-red-600">❌ Invalid jail name</div>', status_code=400
        )
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return HTMLResponse(
            '<div class="text-xs text-red-600">❌ Invalid IP address</div>', status_code=400
        )

    ok = await _fail2ban_unban(jail, ip)
    if ok:
        return HTMLResponse(
            f'<div class="text-xs text-green-600">✅ {ip} sbloccato da {jail}</div>'
        )
    return HTMLResponse(f'<div class="text-xs text-red-600">❌ Impossibile sbloccare {ip}</div>')


@router.get("/security/abuseipdb-blacklist", response_class=HTMLResponse)
async def security_abuseipdb_blacklist(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    settings = get_settings()
    api_key = getattr(settings, "abuseipdb_api_key", "")

    if not api_key:
        return HTMLResponse(
            '<div class="text-red-500 text-sm">No AbuseIPDB API key configured.</div>'
        )

    blacklist = await _abuseipdb_blacklist(api_key)

    if not blacklist:
        return HTMLResponse('<div class="text-sm text-gray-500">No blacklist entries found.</div>')

    html = '<div class="space-y-2">'
    for entry in blacklist:
        color_class = "text-red-500" if entry["score"] > 80 else "text-orange-500"
        html += f"""
        <div class="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-800 rounded">
            <span class="font-mono text-sm">{entry["ip"]}</span>
            <div class="text-xs text-gray-500">
                Score: <span class="{color_class} font-bold">{entry["score"]}</span> |
                Reports: {entry["reports"]}
            </div>
        </div>
        """
    html += "</div>"

    return HTMLResponse(html)


@router.post("/security/abuseipdb-check", response_class=HTMLResponse)
async def security_abuseipdb_check(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    form = await request.form()
    ip = form.get("ip")
    api_key = form.get("api_key")

    if not ip or not api_key:
        return HTMLResponse('<div class="text-red-500 text-sm">IP and API key are required.</div>')

    result = await _abuseipdb_check(ip, api_key)

    if "error" in result:
        return HTMLResponse(f'<div class="text-red-500 text-sm">Error: {result["error"]}</div>')

    score = result.get("score", 0)
    color_class = (
        "text-green-500" if score < 20 else ("text-orange-500" if score < 80 else "text-red-500")
    )

    return HTMLResponse(f'''
    <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded border border-gray-200 "
         "dark:border-gray-700">
        <div class="flex justify-between items-center">
            <span class="font-mono">{result["ip"]}</span>
            <span class="{color_class} font-bold">Score: {score}/100</span>
        </div>
        <div class="text-xs text-gray-500 mt-1">Total Reports: {result.get("reports", 0)}</div>
    </div>
    ''')


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


# Firewall routes
@router.post("/security/firewall/enable", response_class=HTMLResponse)
async def security_firewall_enable(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    client_ip = _get_client_ip(request)
    ssh_port = await _detect_ssh_port()
    ok = await _enable_ufw(client_ip, ssh_port)
    if ok:
        return HTMLResponse('<span class="text-green-600 text-sm">Firewall Enabled</span>')
    return HTMLResponse('<span class="text-red-600 text-sm">Failed to enable firewall</span>')


@router.post("/security/firewall/disable", response_class=HTMLResponse)
async def security_firewall_disable(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    ok = await _disable_ufw()
    if ok:
        return HTMLResponse('<span class="text-yellow-600 text-sm">Firewall Disabled</span>')
    return HTMLResponse('<span class="text-red-600 text-sm">Failed to disable firewall</span>')


@router.post("/security/firewall/rule/add", response_class=HTMLResponse)
async def security_firewall_rule_add(
    request: Request,
    port: str = Form(...),
    protocol: str = Form("tcp"),
    action: str = Form("allow"),
    source: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    ok = await _add_ufw_rule(port, protocol, action, source)
    if ok:
        return HTMLResponse('<span class="text-green-600 text-sm">Rule added</span>')
    return HTMLResponse('<span class="text-red-600 text-sm">Failed to add rule</span>')


@router.post("/security/firewall/rule/delete", response_class=HTMLResponse)
async def security_firewall_rule_delete(
    request: Request,
    index: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    client_ip = _get_client_ip(request)
    ssh_port = await _detect_ssh_port()

    try:
        ok = await _delete_ufw_rule(index, client_ip=client_ip, ssh_port=ssh_port)
        if ok:
            return HTMLResponse('<span class="text-green-600 text-sm">Rule deleted</span>')
        return HTMLResponse('<span class="text-red-600 text-sm">Failed to delete rule</span>')
    except ValueError as e:
        return HTMLResponse(f'<span class="text-red-600 text-sm">{e}</span>', status_code=400)


# Fail2ban config overrides
@router.get("/security/fail2ban/config/{jail}")
async def security_fail2ban_get_config(
    request: Request, jail: str, db: AsyncSession = Depends(get_db)
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    cfg = await _get_jail_config(jail)
    return cfg


@router.post("/security/fail2ban/config/{jail}", response_class=HTMLResponse)
async def security_fail2ban_config(
    request: Request,
    jail: str,
    bantime: int = Form(...),
    findtime: int = Form(...),
    maxretry: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    try:
        ok = await _save_jail_config(jail, bantime=bantime, findtime=findtime, maxretry=maxretry)
        if ok:
            return HTMLResponse(
                '<span class="text-green-600 text-sm">Configuration saved and reloaded</span>'
            )
        return HTMLResponse(
            '<span class="text-red-600 text-sm">Failed to save configuration</span>'
        )
    except ValueError as e:
        return HTMLResponse(f'<span class="text-red-600 text-sm">{e}</span>', status_code=400)


# ClamAV toggle
@router.post("/security/malware/clamav/toggle", response_class=HTMLResponse)
async def security_clamav_toggle(request: Request, db: AsyncSession = Depends(get_db)):
    import asyncio

    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    mem = await get_host_memory_gb()
    if mem < 2.0:
        return HTMLResponse(
            '<div class="text-red-600 text-sm font-semibold">'
            "Insufficient system memory (minimum 2.0 GB RAM required)"
            "</div>",
            status_code=400,
        )

    proc = await asyncio.create_subprocess_exec(
        "docker",
        "ps",
        "--filter",
        "name=pit-panel-clamav",
        "--format",
        "{{.Status}}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    status = stdout.decode().strip()

    if status:
        await asyncio.create_subprocess_exec(
            "docker",
            "stop",
            "pit-panel-clamav",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return HTMLResponse('<span class="text-yellow-600">ClamAV container stopped</span>')
    else:
        proc_exist = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "-a",
            "--filter",
            "name=pit-panel-clamav",
            "--format",
            "{{.Names}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_exist, _ = await proc_exist.communicate()
        exists = stdout_exist.decode().strip()

        if exists:
            await asyncio.create_subprocess_exec(
                "docker",
                "start",
                "pit-panel-clamav",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc_img = await asyncio.create_subprocess_exec(
                "docker",
                "image",
                "inspect",
                "clamav/clamav:latest",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc_img.communicate()
            if proc_img.returncode != 0:
                await asyncio.create_subprocess_exec(
                    "docker",
                    "pull",
                    "clamav/clamav:latest",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            await asyncio.create_subprocess_exec(
                "docker",
                "run",
                "-d",
                "--name",
                "pit-panel-clamav",
                "-p",
                "127.0.0.1:3310:3310",
                "-v",
                "/:/host:ro",
                "clamav/clamav:latest",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        return HTMLResponse('<span class="text-green-600">ClamAV container started</span>')


# Lynis System Audit endpoints
@router.post("/security/lynis/audit", response_class=HTMLResponse)
async def security_lynis_audit(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    background_tasks.add_task(run_lynis_audit)
    return HTMLResponse('<span class="text-green-600">System audit started in background</span>')


@router.get("/security/lynis/report")
async def security_lynis_report(request: Request, db: AsyncSession = Depends(get_db)):
    import json

    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    cache_path = "/var/lib/pit-panel/lynis_last_report.json"
    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        return {"status": "error", "error": f"No audit report found: {e}"}

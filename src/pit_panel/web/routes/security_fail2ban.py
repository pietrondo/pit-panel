"""Fail2ban routes — enable jails, view banned IPs, unban, config overrides."""

import asyncio
import contextlib
import html as html_mod
import ipaddress
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.security import (
    _fail2ban_jail_banned,
    _fail2ban_unban,
    _get_jail_config,
    _save_jail_config,
)
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin

router = APIRouter()


@router.post("/security/fail2ban/enable", response_class=HTMLResponse)
async def security_fail2ban_enable(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    form = await request.form()
    jail = str(form.get("jail", ""))

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse(
            '<span class="text-red-600 text-xs">❌ Invalid jail name</span>', status_code=400
        )
    jail_escaped = html_mod.escape(jail)

    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "fail2ban-client",
            "start",
            jail,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return HTMLResponse(
                f'<span class="text-green-600 text-xs">✅ {jail_escaped} enabled</span>'
            )
        return HTMLResponse(
            f'<span class="text-red-600 text-xs">❌ {jail_escaped}: '
            f"{stderr.decode().strip()[:100]}</span>"
        )
    except FileNotFoundError:
        return HTMLResponse(
            '<span class="text-yellow-600 text-xs">fail2ban-client not found</span>'
        )
    except Exception as e:
        with contextlib.suppress(Exception):
            if "proc" in locals():
                proc.kill()
        return HTMLResponse(f'<span class="text-red-600 text-xs">Error: {e}</span>')


@router.get("/security/fail2ban/jail/{jail}", response_class=HTMLResponse)
async def security_fail2ban_jail(request: Request, jail: str, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse(
            '<div class="text-xs text-red-500">Invalid jail name</div>', status_code=400
        )

    jailed = await _fail2ban_jail_banned(jail)
    jail_e = html_mod.escape(jail)

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


@router.get("/security/fail2ban/config/{jail}")
async def security_fail2ban_get_config(
    request: Request, jail: str, db: AsyncSession = Depends(get_db)
):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse("Invalid jail name", status_code=400)

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

    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", jail):
        return HTMLResponse(
            '<span class="text-red-600 text-sm">Invalid jail name</span>', status_code=400
        )

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

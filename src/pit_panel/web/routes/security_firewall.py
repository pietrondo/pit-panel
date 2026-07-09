"""Firewall (UFW) routes — enable, disable, add/delete rules."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.security import (
    _add_ufw_rule,
    _delete_ufw_rule,
    _detect_ssh_port,
    _disable_ufw,
    _enable_ufw,
    _get_client_ip,
)
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin

router = APIRouter()


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

    import re

    if action not in ("allow", "deny"):
        return HTMLResponse(
            '<span class="text-red-600 text-sm">Invalid action</span>',
            status_code=400,
        )
    if protocol not in ("tcp", "udp", "any"):
        return HTMLResponse(
            '<span class="text-red-600 text-sm">Invalid protocol</span>',
            status_code=400,
        )
    if not re.match(r"^[a-zA-Z0-9]+$", port) and port != "any":
        return HTMLResponse(
            '<span class="text-red-600 text-sm">Invalid port</span>',
            status_code=400,
        )
    if source:
        import ipaddress

        try:
            ipaddress.ip_network(source, strict=False)
        except ValueError:
            return HTMLResponse(
                '<span class="text-red-600 text-sm">Invalid source IP or network</span>',
                status_code=400,
            )

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

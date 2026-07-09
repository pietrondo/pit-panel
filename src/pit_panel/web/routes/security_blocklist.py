"""Blocklist routes — import IP blocklists from external sources."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.blocklist import BLOCKLIST_SOURCES, fetch_blocklist
from pit_panel.db.session import get_db
from pit_panel.security.ipban import ban_ips_bulk
from pit_panel.web.deps import get_admin

router = APIRouter()


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

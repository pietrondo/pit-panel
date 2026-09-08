"""Lynis system audit routes."""

import json
from typing import Any

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.security import run_lynis_audit
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin

router = APIRouter()


@router.post("/security/lynis/audit", response_class=HTMLResponse)  # type: ignore[untyped-decorator]
async def security_lynis_audit(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    background_tasks.add_task(run_lynis_audit)
    return HTMLResponse('<span class="text-green-600">System audit started in background</span>')


@router.get("/security/lynis/report", response_class=HTMLResponse)  # type: ignore[untyped-decorator]
async def security_lynis_report(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    cache_path = "/var/lib/pit-panel/lynis_last_report.json"

    try:
        async with aiofiles.open(cache_path, encoding="utf-8") as f:
            content = await f.read()
            report_data = dict(json.loads(content))
            return HTMLResponse(f"<pre class='text-xs text-gray-500 overflow-auto max-h-64'>{json.dumps(report_data, indent=2)}</pre>")
    except Exception as e:
        return HTMLResponse(f"<div class='text-red-500 text-sm'>No audit report found: {e}</div>")

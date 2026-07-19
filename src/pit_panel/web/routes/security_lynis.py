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


@router.post("/security/lynis/audit", response_class=HTMLResponse) # type: ignore[untyped-decorator]
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


@router.get("/security/lynis/report") # type: ignore[untyped-decorator]
async def security_lynis_report(request: Request, db: AsyncSession = Depends(get_db)) -> Any:
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    cache_path = "/var/lib/pit-panel/lynis_last_report.json"

    try:
        async with aiofiles.open(cache_path, encoding="utf-8") as f:
            content = await f.read()
            return dict(json.loads(content))
    except Exception as e:
        return {"status": "error", "error": f"No audit report found: {e}"}

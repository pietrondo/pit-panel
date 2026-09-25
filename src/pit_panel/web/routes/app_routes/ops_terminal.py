"""App terminal: interactive shell into the main compose service."""

import asyncio
from pathlib import Path

from fastapi import Depends, Request, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

from .ops_files import _stream_websocket
from .router import router


def _find_main_service(compose_path: Path) -> str | None:
    """Return the first non-db service name from docker-compose.yml."""
    import yaml

    try:
        with open(compose_path) as f:
            data = yaml.safe_load(f)
        if not data or "services" not in data:
            return None
        db_keywords = ("db", "mysql", "postgres", "mariadb", "redis", "database")
        for name in data["services"]:
            if name not in db_keywords:
                return name
        return None
    except Exception:
        return None


@router.get("/apps/{sd_id}/terminal", response_class=HTMLResponse)
async def app_terminal_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse(url=f"/auth/login?next=/apps/{sd_id}/terminal")

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return RedirectResponse("/apps", status_code=302)

    settings = get_settings()
    compose_path = Path(settings.apps_dir) / sd.subdomain / "docker-compose.yml"
    service = _find_main_service(compose_path) or "wordpress"

    return render("terminal.html", request=request, sd=sd, service=service)


@router.websocket("/apps/{sd_id}/terminal/ws")
async def app_terminal_ws(websocket: WebSocket, sd_id: int, db: AsyncSession = Depends(get_db)):
    await websocket.accept()

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        await websocket.send_text("ERROR: App not found")
        await websocket.close()
        return

    settings = get_settings()
    compose_path = Path(settings.apps_dir) / sd.subdomain / "docker-compose.yml"
    service = _find_main_service(compose_path) or "wordpress"
    cwd = str(Path(settings.apps_dir) / sd.subdomain)

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            str(compose_path),
            "exec",
            "-T",
            service,
            "sh",
            "-i",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
    except OSError as e:
        await websocket.send_text(f"ERROR: {e}")
        await websocket.close()
        return

    await _stream_websocket(websocket, proc, forward_stdin=True)

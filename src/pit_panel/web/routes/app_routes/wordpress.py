"""WordPress-specific routes: proxy, auto-login, cache/plugin/core management."""

import asyncio
import logging
import os

from fastapi import Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.docker_ops import DockerManager
from pit_panel.core.wp_proxy import auto_login as wp_auto_login
from pit_panel.core.wp_proxy import proxy_request as wp_proxy_request
from pit_panel.core.wp_proxy import read_env as wp_read_env
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user

from .router import router

logger = logging.getLogger(__name__)


def _get_wp_port(settings, subdomain: str) -> int | None:
    env = wp_read_env(settings.apps_dir, subdomain)
    port_str = env.get("PORT", "8081")
    try:
        return int(port_str)
    except ValueError:
        return None


def _fix_cookie_path_static(cookie: str, prefix: str) -> str:
    parts = cookie.split(";")
    fixed = []
    for part in parts:
        part = part.strip()
        if part.lower().startswith("path="):
            path_val = part.split("=", 1)[1]
            if not path_val.startswith(prefix):
                part = f"path={prefix}{path_val}"
        fixed.append(part)
    return "; ".join(fixed)


async def _run_wp_cli(settings, subdomain: str, wp_args: list[str]) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "exec",
        "-T",
        "wordpress",
        "wp",
        *wp_args,
        "--allow-root",
        cwd=os.path.join(settings.apps_dir, subdomain),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return {"returncode": proc.returncode, "stdout": stdout.decode(), "stderr": stderr.decode()}


@router.post("/apps/{sd_id}/wp/flush-cache", response_class=HTMLResponse)
async def app_wp_flush_cache(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<span class='text-red-500 text-xs'>App not found</span>")
    settings = get_settings()

    try:
        r = await _run_wp_cli(settings, sd.subdomain, ["cache", "flush"])
        if r["returncode"] != 0:
            return HTMLResponse(f"<span class='text-red-500 text-xs'>Error: {r['stderr']}</span>")
    except Exception as e:
        return HTMLResponse(f"<span class='text-red-500 text-xs'>Exception: {e}</span>")

    return HTMLResponse(
        "<span class='text-green-600 text-sm font-medium p-2 bg-green-50 rounded dark:bg-green-900/30 dark:text-green-400'>Cache flushed successfully!</span>"  # noqa: E501
    )


@router.post("/apps/{sd_id}/wp/update-plugins", response_class=HTMLResponse)
async def app_wp_update_plugins(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<span class='text-red-500 text-xs'>App not found</span>")
    settings = get_settings()

    try:
        r = await _run_wp_cli(settings, sd.subdomain, ["plugin", "update", "--all"])
        if r["returncode"] != 0:
            return HTMLResponse(f"<span class='text-red-500 text-xs'>Error: {r['stderr']}</span>")
    except Exception as e:
        return HTMLResponse(f"<span class='text-red-500 text-xs'>Exception: {e}</span>")

    return HTMLResponse(
        "<span class='text-green-600 text-sm font-medium p-2 bg-green-50 rounded dark:bg-green-900/30 dark:text-green-400'>Plugins updated successfully!</span>"  # noqa: E501
    )


@router.post("/apps/{sd_id}/wp/update-core", response_class=HTMLResponse)
async def app_wp_update_core(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<span class='text-red-500 text-xs'>App not found</span>")
    settings = get_settings()

    try:
        r = await _run_wp_cli(settings, sd.subdomain, ["core", "update"])
        if r["returncode"] != 0:
            return HTMLResponse(f"<span class='text-red-500 text-xs'>Error: {r['stderr']}</span>")
    except Exception as e:
        return HTMLResponse(f"<span class='text-red-500 text-xs'>Exception: {e}</span>")

    return HTMLResponse(
        "<span class='text-green-600 text-sm font-medium p-2 bg-green-50 rounded dark:bg-green-900/30 dark:text-green-400'>Core updated successfully!</span>"  # noqa: E501
    )


@router.get("/apps/{sd_id}/wp-auto-login")
async def app_wp_auto_login(
    request: Request, sd_id: int, db: AsyncSession = Depends(get_db)
):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse(url=f"/auth/login?next=/apps/{sd_id}")

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd or sd.app_type != "wordpress":
        return RedirectResponse(url="/apps", status_code=302)

    settings = get_settings()
    port = _get_wp_port(settings, sd.subdomain)
    if not port:
        return HTMLResponse("WordPress port not found", status_code=500)

    panel_fqdn = request.url.hostname or sd.subdomain + "." + settings.base_domain
    result = await wp_auto_login(settings.apps_dir, sd.subdomain, port, panel_fqdn)
    if not result:
        return RedirectResponse(url=f"https://{sd.subdomain}.{settings.base_domain}/wp-admin")

    redirect_to, cookies = result
    prefix = f"/apps/{sd_id}/wp"
    redirect_to = f"{prefix}{redirect_to}" if redirect_to.startswith("/") else f"{prefix}/wp-admin/"

    response = RedirectResponse(url=redirect_to, status_code=302)
    for cookie_raw in cookies:
        fixed = _fix_cookie_path_static(cookie_raw, prefix)
        response.headers.append("set-cookie", fixed)
    return response


@router.post("/apps/{sd_id}/wp-fix-url", response_class=HTMLResponse)
async def app_wp_fix_url(
    request: Request, sd_id: int, db: AsyncSession = Depends(get_db)
):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("Unauthorized", status_code=401)
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd or sd.app_type != "wordpress":
        return HTMLResponse("Not a WordPress app", status_code=400)

    settings = get_settings()
    base_domain = sd.base_domain or settings.base_domain
    fqdn = f"{sd.subdomain}.{base_domain}"
    docker_mgr = DockerManager(settings.apps_dir)

    success = False
    error_msg = ""
    try:
        r = await docker_mgr.exec_command(sd.subdomain, "wordpress", [
            "sh", "-c",
            f"php -d memory_limit=256M /tmp/wp-cli.phar option update siteurl 'https://{fqdn}'"
            f" && php -d memory_limit=256M /tmp/wp-cli.phar option update home 'https://{fqdn}'"
        ])
        success = r.get("exit_code", -1) == 0
        if not success:
            error_msg = r.get("stderr", "Unknown error")[:300]
    except Exception as e:
        error_msg = str(e)

    msg = f"WordPress URL aggiornata a https://{fqdn}" if success else f"Errore: {error_msg}"
    cls = "text-green-600" if success else "text-red-600"
    return HTMLResponse(f'<p class="text-sm {cls}">{msg}</p>')


@router.api_route("/apps/{sd_id}/wp/{path:path}", methods=[
    "GET", "POST", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS",
])
async def app_wp_proxy(
    request: Request, sd_id: int, path: str, db: AsyncSession = Depends(get_db)
):
    user = await get_user(request, db)
    if not user:
        return Response("Unauthorized", status_code=401)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return Response("App not found", status_code=404)

    settings = get_settings()
    port = _get_wp_port(settings, sd.subdomain)
    if not port:
        return Response("WordPress port not found", status_code=500)

    return await wp_proxy_request(request, port, sd_id)

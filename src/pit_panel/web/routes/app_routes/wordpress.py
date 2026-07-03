"""WordPress-specific routes: proxy, auto-login, cache/plugin/core management."""

import asyncio
import base64
import logging
import os
from pathlib import Path

from fastapi import Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.docker_ops import DockerManager
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


async def _run_wp_cli(settings, subdomain: str, wp_args: list[str]) -> dict:
    cwd = os.path.join(settings.apps_dir, subdomain)
    # Ensure wp-cli phar is available
    dl_proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "-f",
        os.path.join(cwd, "docker-compose.yml"),
        "exec",
        "-T",
        "wordpress",
        "sh",
        "-c",
        "test -f /tmp/wp-cli.phar || curl -sSLo /tmp/wp-cli.phar"
        " https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar",
        cwd=cwd,
    )
    await dl_proc.wait()

    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "-f",
        os.path.join(cwd, "docker-compose.yml"),
        "exec",
        "-T",
        "wordpress",
        "php",
        "/tmp/wp-cli.phar",
        *wp_args,
        "--allow-root",
        cwd=cwd,
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
async def app_wp_auto_login(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse(url=f"/auth/login?next=/apps/{sd_id}")

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd or sd.app_type != "wordpress":
        return RedirectResponse(url="/apps", status_code=302)

    settings = get_settings()
    base_domain = sd.base_domain or settings.base_domain
    fqdn = f"{sd.subdomain}.{base_domain}"

    docker_mgr = DockerManager(settings.apps_dir)

    # Step 1: ensure WP-CLI phar is available
    try:
        await docker_mgr.exec_command(
            sd.subdomain,
            "wordpress",
            [
                "sh",
                "-c",
                "test -f /tmp/wp-cli.phar || curl -sSLo /tmp/wp-cli.phar"
                " https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar",
            ],
        )
    except Exception as e:
        logger.warning(f"WP-CLI download failed for {sd.subdomain}: {e}")

    # Step 2: fix site URL
    try:
        await docker_mgr.exec_command(
            sd.subdomain,
            "wordpress",
            [
                "sh",
                "-c",
                f"php -d memory_limit=256M /tmp/wp-cli.phar --allow-root"
                f" option update siteurl 'https://{fqdn}'"
                f" && php -d memory_limit=256M /tmp/wp-cli.phar --allow-root"
                f" option update home 'https://{fqdn}'",
            ],
        )
    except Exception as e:
        logger.warning(f"WP-CLI site URL fix failed for {sd.subdomain}: {e}")

    # Step 3: ensure the auth-handler PHP file exists in WordPress web root
    handler_path = Path(settings.apps_dir) / sd.subdomain / ".pit-auth-handler.php"
    if not handler_path.exists():
        handler_code = """<?php
require_once dirname(__DIR__).'/wp-load.php';
$t=$_GET['token']??'';
if(!$t)die();
$d=get_transient('pit_'.$t);
if(!$d)die();
delete_transient('pit_'.$t);
$c=json_decode($d,true)?:[];
foreach($c as $n=>$v)setcookie($n,$v,time()+86400,COOKIEPATH,COOKIE_DOMAIN,true,true);
header('Location: /wp-admin/');
"""
        handler_path.write_text(handler_code)
        try:
            await docker_mgr.exec_command(
                sd.subdomain,
                "wordpress",
                [
                    "sh",
                    "-c",
                    "mkdir -p wp-content",
                ],
            )
            b64 = base64.b64encode(handler_code.encode()).decode()
            await docker_mgr.exec_command(
                sd.subdomain,
                "wordpress",
                [
                    "sh",
                    "-c",
                    f"echo '{b64}' | base64 -d > wp-content/pit-auth.php",
                ],
            )
            logger.info("wp_auto_login[%s]: auth handler installed", sd.subdomain)
        except Exception as e:
            logger.warning(f"Auth handler install failed for {sd.subdomain}: {e}")

    # Step 4: generate auth cookies and store as transient
    token = base64.urlsafe_b64encode(os.urandom(12)).rstrip(b"=").decode()
    php_code = (
        "$id=1;$exp=time()+86400;"
        '$li=wp_generate_auth_cookie($id,$exp,"logged_in");'
        '$sa=wp_generate_auth_cookie($id,$exp,"secure_auth");'
        '$au=wp_generate_auth_cookie($id,$exp,"auth");'
        "set_transient("
        f"  'pit_{token}',"
        "  json_encode(array("
        "    LOGGED_IN_COOKIE=>$li,"
        "    SECURE_AUTH_COOKIE=>$sa,"
        "    AUTH_COOKIE=>$au"
        "  )),"
        "  30"
        ");"
        'echo json_encode(array("ok"=>true));'
    )
    try:
        r = await docker_mgr.exec_command(
            sd.subdomain,
            "wordpress",
            [
                "php",
                "-d",
                "memory_limit=256M",
                "/tmp/wp-cli.phar",
                "--allow-root",
                "eval",
                php_code,
            ],
        )
        if r.get("success"):
            logger.info("wp_auto_login[%s]: transient stored, redirecting to blog", sd.subdomain)
            return RedirectResponse(url=f"https://{fqdn}/wp-content/pit-auth.php?token={token}")
        logger.warning(
            "wp_auto_login[%s]: WP-CLI transient failed: %s",
            sd.subdomain,
            r.get("stderr", "")[:200],
        )
    except Exception as e:
        logger.warning(f"wp_auto_login[%s]: transient error: {e}", sd.subdomain)

    logger.info("wp_auto_login[%s]: fallback to direct https://%s/wp-admin", sd.subdomain, fqdn)
    return RedirectResponse(url=f"https://{fqdn}/wp-admin")


@router.post("/apps/{sd_id}/wp-fix-url", response_class=HTMLResponse)
async def app_wp_fix_url(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
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
        r1 = await docker_mgr.exec_command(
            sd.subdomain,
            "wordpress",
            [
                "php",
                "-d",
                "memory_limit=256M",
                "/tmp/wp-cli.phar",
                "--allow-root",
                "option",
                "update",
                "siteurl",
                f"https://{fqdn}",
            ],
        )
        r2 = await docker_mgr.exec_command(
            sd.subdomain,
            "wordpress",
            [
                "php",
                "-d",
                "memory_limit=256M",
                "/tmp/wp-cli.phar",
                "--allow-root",
                "option",
                "update",
                "home",
                f"https://{fqdn}",
            ],
        )
        success = r1.get("success", False) and r2.get("success", False)
        if not success:
            error_msg = (r1.get("stderr", "") + " " + r2.get("stderr", ""))[:300].strip() or "Unknown error"
    except Exception as e:
        error_msg = str(e)

    msg = f"WordPress URL aggiornata a https://{fqdn}" if success else f"Errore: {error_msg}"
    cls = "text-green-600" if success else "text-red-600"
    return HTMLResponse(f'<p class="text-sm {cls}">{msg}</p>')


@router.api_route(
    "/apps/{sd_id}/proxy/{service_name:path}",
    methods=[
        "GET",
        "POST",
        "HEAD",
        "PUT",
        "DELETE",
        "PATCH",
        "OPTIONS",
    ],
)
async def app_proxy_service(
    request: Request, sd_id: int, service_name: str, db: AsyncSession = Depends(get_db)
):
    user = await get_user(request, db)
    if not user:
        return Response("Unauthorized", status_code=401)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return Response("App not found", status_code=404)

    settings = get_settings()
    env = wp_read_env(settings.apps_dir, sd.subdomain)
    port_map = {
        "phpmyadmin": env.get("PMA_PORT", "8082"),
    }

    parts = service_name.split("/", 1)
    name = parts[0]
    sub_path = parts[1] if len(parts) > 1 else ""

    if not sub_path and not request.url.path.endswith("/"):
        return RedirectResponse(url=request.url.path + "/", status_code=302)

    port_str = port_map.get(name)
    if not port_str:
        return Response(f"Service '{name}' not found", status_code=404)

    try:
        target_port = int(port_str)
    except ValueError:
        return Response(f"Invalid port for '{name}'", status_code=500)

    import httpx

    prefix = f"/apps/{sd_id}/proxy/{name}"
    target_url = f"http://127.0.0.1:{target_port}/{sub_path}"
    qs = request.scope.get("query_string", b"").decode()
    if qs:
        target_url += f"?{qs}"

    headers = {}
    hop_by_hop = frozenset(
        {
            "host",
            "connection",
            "transfer-encoding",
            "content-length",
            "keep-alive",
            "upgrade",
        }
    )
    for key, value in request.headers.items():
        if key.lower() in hop_by_hop:
            continue
        headers[key] = value

    body = await request.body()
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                follow_redirects=False,
            )
        except httpx.ConnectError:
            return Response(f"Service '{name}' unreachable", status_code=502)

    content = resp.content
    content_type = resp.headers.get("content-type", "").lower()
    if any(ct in content_type for ct in ("text/html", "text/css", "application/javascript")):
        rewrite_dirs = ("/js/", "/css/", "/themes/", "/libraries/", "/vendor/")
        for d in rewrite_dirs:
            content = content.replace(f'"{d}'.encode(), f'"{prefix}{d}'.encode())
            content = content.replace(f"'{d}".encode(), f"'{prefix}{d}".encode())

    resp_headers = {}
    for key, value in resp.headers.items():
        kl = key.lower()
        if kl in ("content-encoding", "transfer-encoding", "content-length"):
            continue
        if kl == "location":
            loc = value
            if loc.startswith("/") and not loc.startswith(prefix):
                value = f"{prefix}{loc}"
        resp_headers[key] = value

    return Response(content=content, status_code=resp.status_code, headers=resp_headers)


@router.api_route(
    "/apps/{sd_id}/wp/{path:path}",
    methods=[
        "GET",
        "POST",
        "HEAD",
        "PUT",
        "DELETE",
        "PATCH",
        "OPTIONS",
    ],
)
async def app_wp_proxy(request: Request, sd_id: int, path: str, db: AsyncSession = Depends(get_db)):
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

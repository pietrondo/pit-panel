"""WordPress proxy and auto-login through pit-panel domain."""

import asyncio
import json
import logging
from pathlib import Path

import httpx
from fastapi import Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)

_REWRITE_PREFIXES = ("/wp-admin", "/wp-content", "/wp-includes")
_HOP_BY_HOP = frozenset({"host", "connection", "transfer-encoding", "keep-alive", "upgrade"})


def read_env(apps_dir: str, subdomain: str) -> dict[str, str]:
    env_path = Path(apps_dir) / subdomain / ".env"
    if not env_path.exists():
        return {}
    env_vars = {}
    for line in env_path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()
    return env_vars


def _rewrite_urls(content: bytes, prefix: str) -> bytes:
    for p in _REWRITE_PREFIXES:
        content = content.replace(p.encode(), f"{prefix}{p}".encode())
    return content


def _rewrite_content(content: bytes, content_type: str, prefix: str) -> bytes:
    if any(
        ct in content_type
        for ct in (
            "text/html",
            "text/css",
            "application/javascript",
            "application/json",
            "text/xml",
            "application/xml",
        )
    ):
        return _rewrite_urls(content, prefix)
    return content


def _fix_cookie_path(cookie: str, prefix: str) -> str:
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


def _fix_location(location: str, prefix: str) -> str:
    if location.startswith("/") and not location.startswith(prefix):
        return f"{prefix}{location}"
    return location


async def auto_login(
    apps_dir: str,
    subdomain: str,
    port: int,
    panel_fqdn: str,
) -> tuple[str, list[str]] | None:
    """
    Generate WordPress auth cookies via WP-CLI eval, bypassing wp-login.php.

    This avoids the test-cookie dance, redirect loops, and password-hash
    mismatches between CLI and web contexts that plague POST-based login.
    wp_set_auth_cookie() creates a proper session token in the DB and
    generates the same cookie values WordPress uses on a normal login.
    """
    env = read_env(apps_dir, subdomain)
    wp_pass = env.get("WP_ADMIN_PASSWORD", "")
    if not wp_pass:
        logger.info("auto_login[%s]: no WP_ADMIN_PASSWORD in .env", subdomain)
        return None

    compose_dir = Path(apps_dir) / subdomain
    compose_file = compose_dir / "docker-compose.yml"

    php_code = (
        "$id=1;"
        "$exp=time()+86400;"
        '$li=wp_generate_auth_cookie($id,$exp,"logged_in");'
        '$sa=wp_generate_auth_cookie($id,$exp,"secure_auth");'
        '$au=wp_generate_auth_cookie($id,$exp,"auth");'
        "echo json_encode(array("
        '"cookies"=>array('
        'LOGGED_IN_COOKIE."=".$li."; Path=/; HttpOnly",'
        'SECURE_AUTH_COOKIE."=".$sa."; Path=/wp-admin; HttpOnly",'
        'AUTH_COOKIE."=".$au."; Path=/wp-admin; HttpOnly"'
        "),"
        '"redirect_to"=>admin_url()'
        "));"
    )

    logger.info("auto_login[%s]: running WP-CLI eval to generate auth cookies", subdomain)

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "wordpress",
            "php",
            "-d",
            "memory_limit=256M",
            "/tmp/wp-cli.phar",
            "--allow-root",
            "eval",
            php_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(compose_dir),
        )
        stdout, stderr = await proc.communicate()
    except OSError as e:
        logger.error("auto_login[%s]: subprocess error: %s", subdomain, e)
        return None

    if proc.returncode != 0:
        logger.warning(
            "auto_login[%s]: WP-CLI eval failed (rc=%d): %s",
            subdomain,
            proc.returncode,
            stderr.decode()[:300],
        )
        return None

    try:
        data = json.loads(stdout.decode())
        cookies = data.get("cookies", [])
        redirect_to = data.get("redirect_to", "/wp-admin/")
        if not cookies:
            logger.warning("auto_login[%s]: WP-CLI returned no cookies", subdomain)
            return None
        logger.info(
            "auto_login[%s]: WP-CLI success → %s (%d cookies)",
            subdomain,
            redirect_to,
            len(cookies),
        )
        return redirect_to, cookies
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(
            "auto_login[%s]: failed to parse WP-CLI output: %s — raw: %s",
            subdomain,
            e,
            stdout.decode()[:300],
        )
        return None


async def proxy_request(
    request: Request,
    port: int,
    sd_id: int,
) -> Response:
    path = request.path_params.get("path", "")
    prefix = f"/apps/{sd_id}/wp"

    target_url = f"http://localhost:{port}/{path}"
    qs = request.scope.get("query_string", b"").decode()
    if qs:
        target_url += f"?{qs}"

    headers = {}
    for key, value in request.headers.items():
        kl = key.lower()
        if kl in _HOP_BY_HOP:
            continue
        if kl == "host":
            headers[key] = f"localhost:{port}"
        else:
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
            return Response("WordPress container unreachable", status_code=502)

    content = resp.content
    content_type = resp.headers.get("content-type", "")
    content = _rewrite_content(content, content_type, prefix)

    resp_headers = {}
    for key, value in resp.headers.items():
        kl = key.lower()
        if kl in ("content-encoding", "transfer-encoding", "content-length"):
            continue
        if kl == "set-cookie":
            # httpx Headers.get_list returns all values for multi-value headers
            for v in resp.headers.get_list("set-cookie"):
                resp_headers["set-cookie"] = _fix_cookie_path(v, prefix)
            continue
        if kl == "location":
            value = _fix_location(value, prefix)
        resp_headers[key] = value

    return Response(
        content=content,
        status_code=resp.status_code,
        headers=resp_headers,
    )

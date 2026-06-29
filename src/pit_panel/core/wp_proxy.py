"""WordPress proxy and auto-login through pit-panel domain."""

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
    if any(ct in content_type for ct in (
        "text/html", "text/css", "application/javascript",
        "application/json", "text/xml", "application/xml",
    )):
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
    env = read_env(apps_dir, subdomain)
    wp_user = env.get("WP_ADMIN_USER", "admin")
    wp_pass = env.get("WP_ADMIN_PASSWORD", "")
    if not wp_pass:
        return None

    async with httpx.AsyncClient() as client:
        # Step 1: GET wp-login.php to get the test cookie
        await client.get(
            f"http://localhost:{port}/wp-login.php",
            headers={"Host": panel_fqdn},
        )

        # Step 2: POST credentials with the test cookie from step 1
        resp = await client.post(
            f"http://localhost:{port}/wp-login.php",
            data={
                "log": wp_user,
                "pwd": wp_pass,
                "redirect_to": "/wp-admin/",
                "testcookie": "1",
            },
            headers={"Host": panel_fqdn},
            follow_redirects=False,
        )

    # WordPress returns 302 with Set-Cookie on success
    cookies = resp.headers.get_list("set-cookie")
    redirect_to = resp.headers.get("location", "/wp-admin/")
    return redirect_to, cookies


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

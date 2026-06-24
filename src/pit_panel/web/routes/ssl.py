"""SSL certificate management routes via Caddy admin API."""

import contextlib
import subprocess
from pathlib import Path

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.db.models import User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token, validate_session
from pit_panel.web.render import render
from pit_panel.web.router import router

CADDYFILE_PATH = "/etc/caddy/Caddyfile"

ACME_PROVIDERS = [
    ("letsencrypt", "Let's Encrypt (default, free, zero config)"),
    ("zerossl", "ZeroSSL (free, needs EAB key from zerossl.com)"),
    ("buypass", "Buypass Go SSL (free, no account needed)"),
    ("google", "Google Trust Services (free, needs EAB from cloud.google.com)"),
]

DNS_PROVIDERS = [
    ("", "None (HTTP-01)"),
    ("cloudflare", "Cloudflare"),
    ("digitalocean", "DigitalOcean"),
    ("route53", "AWS Route53"),
    ("duckdns", "DuckDNS"),
    ("acmedns", "ACME-DNS"),
    ("gandi", "Gandi"),
    ("namecheap", "Namecheap"),
    ("porkbun", "Porkbun"),
    ("ovh", "OVH"),
]


def _generate_caddyfile(
    email: str,
    domain: str,
    panel_sub: str,
    dns_provider: str = "",
    api_var: str = "CF_API_TOKEN",
    acme_provider: str = "letsencrypt",
    eab_key_id: str = "",
    eab_hmac: str = "",
) -> str:
    tls_block = ""
    if dns_provider:
        tls_block = f"dns {dns_provider} {{env.{api_var}}}"

    acme_cfg = ""
    if acme_provider == "zerossl":
        acme_cfg = f'issuer zerossl {{eab "{eab_key_id}" "{eab_hmac}"}}'
    elif acme_provider == "buypass":
        acme_cfg = "issuer buypass"
    elif acme_provider == "google":
        acme_cfg = f'issuer google {{eab "{eab_key_id}" "{eab_hmac}"}}'
    elif acme_provider == "letsencrypt":
        acme_cfg = "issuer acme"

    tls_lines = ""
    if tls_block or acme_cfg:
        inner = "\n        ".join(filter(None, [acme_cfg, tls_block]))
        tls_lines = f"""    tls {{
        {inner}
    }}"""

    if dns_provider:
        return f"""{{
    email {email}
}}

*.{domain}, {domain} {{
{tls_lines}
    @panel host {panel_sub}.{domain}
    handle @panel {{
        reverse_proxy 127.0.0.1:8080
    }}
    handle {{
        respond "pit-panel" 200
    }}
}}
"""
    else:
        acme_clause = ""
        if acme_cfg and acme_cfg != "issuer acme":
            acme_clause = f"""
    tls {{
        {acme_cfg}
    }}"""

        return f"""{{
    email {email}
}}

{panel_sub}.{domain} {{{acme_clause}
    reverse_proxy 127.0.0.1:8080
}}
"""


def _check_caddy_running() -> bool:
    with contextlib.suppress(Exception):
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "caddy"],
            timeout=5,
        )
        return result.returncode == 0
    return False


def _check_port80() -> bool:
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(1)
        s.bind(("0.0.0.0", 80))
        s.close()
        return True
    except OSError:
        return False


async def _get_admin(request: Request, db: AsyncSession) -> User | None:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    data = unsign_session_token, validate_session(settings, cookie)
    if not data:
        return None
    user = await validate_session(db, cookie, settings, data.get("uid", 0))
    if user and user.is_admin:
        return user
    return None


@router.get("/ssl", response_class=HTMLResponse)
async def ssl_setup(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    caddy = CaddyManager(settings.caddy_admin_url)
    certs = await caddy.get_certificates()

    caddy_running = _check_caddy_running()
    port80_free = _check_port80()

    existing = ""
    if Path(CADDYFILE_PATH).exists():
        existing = Path(CADDYFILE_PATH).read_text()[:2000]

    return render(
        "ssl.html",
        user=user,
        settings=settings,
        certs=certs,
        renew_result=None,
        caddy_running=caddy_running,
        port80_free=port80_free,
        acme_providers=ACME_PROVIDERS,
        providers=DNS_PROVIDERS,
        current_caddyfile=existing,
        caddy_result=None,
    )


@router.post("/ssl/generate", response_class=HTMLResponse)
async def ssl_generate(
    request: Request,
    email: str = Form("admin@localhost"),
    acme_provider: str = Form("letsencrypt"),
    dns_provider: str = Form(""),
    api_var: str = Form("CF_API_TOKEN"),
    api_token: str = Form(""),
    eab_key_id: str = Form(""),
    eab_hmac: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    domain = settings.effective_domain
    panel_sub = settings.panel_subdomain

    caddyfile = _generate_caddyfile(
        email, domain, panel_sub, dns_provider, api_var, acme_provider, eab_key_id, eab_hmac
    )
    result_msg = ""

    # Load via Caddy admin API (no file write needed for Caddyfile)
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{get_settings().caddy_admin_url}/load",
                content=caddyfile.encode(),
                headers={"Content-Type": "text/caddyfile"},
                timeout=10,
            )
            if resp.status_code == 200:
                result_msg = "Config loaded. Caddy will provision SSL certificates now."
            else:
                result_msg = f"Caddy API error: HTTP {resp.status_code}. Is Caddy running?"
    except Exception:
        result_msg = (
            "Caddy admin API not reachable. Make sure Caddy is installed and running: "
            "systemctl start caddy"
        )

    # Store API token for DNS-01 providers (Caddy reads from env)
    if api_token and dns_provider:
        try:
            env_path = Path("/etc/caddy/.env")
            env_line = f"{api_var}={api_token}\n"
            if env_path.exists():
                content = env_path.read_text()
                if api_var not in content:
                    env_path.write_text(content + env_line)
            else:
                env_path.write_text(env_line)
            result_msg += " API token saved."
        except (PermissionError, OSError):
            result_msg += " (API token not saved — set manually in /etc/caddy/.env)"

    caddy = CaddyManager(settings.caddy_admin_url)
    certs = await caddy.get_certificates()

    return render(
        "ssl.html",
        user=user,
        settings=settings,
        certs=certs,
        renew_result=None,
        caddy_running=_check_caddy_running(),
        port80_free=_check_port80(),
        acme_providers=ACME_PROVIDERS,
        providers=DNS_PROVIDERS,
        current_caddyfile=caddyfile[:2000],
        caddy_result=result_msg,
    )


@router.post("/ssl/renew", response_class=HTMLResponse)
async def ssl_renew(
    request: Request,
    domain: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    caddy = CaddyManager(settings.caddy_admin_url)
    result = await caddy.renew_certificate(domain)

    certs = await caddy.get_certificates()
    return render(
        "ssl.html",
        user=user,
        settings=settings,
        certs=certs,
        renew_result=result,
        caddy_running=_check_caddy_running(),
        port80_free=_check_port80(),
        acme_providers=ACME_PROVIDERS,
        providers=DNS_PROVIDERS,
        current_caddyfile=(
            Path(CADDYFILE_PATH).read_text()[:2000]
            if Path(CADDYFILE_PATH).exists()
            else ""
        ),
        caddy_result=None,
    )

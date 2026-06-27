"""SSL certificate management routes via Caddy admin API."""

import contextlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()

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


def _sanitize(val: str) -> str:
    if not val:
        return ""
    # Strip dangerous characters that could break out of a Caddyfile value
    return (
        val.replace("\r", "").replace("\n", "").replace('"', "").replace("{", "").replace("}", "")
    )


def _get_acme_config(
    acme_provider: str,
    eab_key_id: str,
    eab_hmac: str,
) -> str:
    eab_key_id = _sanitize(eab_key_id)
    eab_hmac = _sanitize(eab_hmac)
    if acme_provider == "zerossl":
        return f'issuer zerossl {{eab "{eab_key_id}" "{eab_hmac}"}}'
    if acme_provider == "buypass":
        return "issuer buypass"
    if acme_provider == "google":
        return f'issuer google {{eab "{eab_key_id}" "{eab_hmac}"}}'
    if acme_provider == "letsencrypt":
        return "issuer acme"
    return ""


def _get_tls_block(acme_cfg: str, dns_provider: str, api_var: str) -> str:
    parts = []
    if acme_cfg:
        parts.append(acme_cfg)
    if dns_provider:
        parts.append(f"dns {dns_provider} {{env.{api_var}}}")

    if not parts:
        return ""

    inner = "\n        ".join(parts)
    return f"""    tls {{
        {inner}
    }}"""


@dataclass
class CaddyfileConfig:
    email: str
    domain: str
    panel_sub: str
    dns_provider: str = ""
    api_var: str = "CF_API_TOKEN"
    acme_provider: str = "letsencrypt"
    eab_key_id: str = ""
    eab_hmac: str = ""


def _generate_caddyfile(config: CaddyfileConfig) -> str:
    email = _sanitize(config.email)
    domain = _sanitize(config.domain)
    panel_sub = _sanitize(config.panel_sub)
    dns_provider = _sanitize(config.dns_provider)
    api_var = _sanitize(config.api_var)

    acme_cfg = _get_acme_config(config.acme_provider, config.eab_key_id, config.eab_hmac)

    if dns_provider:
        tls_lines = _get_tls_block(acme_cfg, dns_provider, api_var)
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
            acme_clause = "\n" + _get_tls_block(acme_cfg, "", "")

        if acme_clause:
            return f"""{{
    email {email}
}}

{panel_sub}.{domain} {{{acme_clause}
    reverse_proxy 127.0.0.1:8080
}}
"""
        else:
            return f"""{panel_sub}.{domain} {{
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


@router.get("/ssl", response_class=HTMLResponse)
async def ssl_setup(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
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
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    domain = settings.effective_domain
    panel_sub = settings.panel_subdomain

    caddy_config = CaddyfileConfig(
        email=email,
        domain=domain,
        panel_sub=panel_sub,
        dns_provider=dns_provider,
        api_var=api_var,
        acme_provider=acme_provider,
        eab_key_id=eab_key_id,
        eab_hmac=eab_hmac,
    )
    caddyfile = _generate_caddyfile(caddy_config)

    result_msg = ""

    # Write Caddyfile directly and reload (avoids caddy adapt formatting issues)
    try:
        Path(CADDYFILE_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(CADDYFILE_PATH).write_text(caddyfile)
        reload_result = subprocess.run(
            ["sudo", "-n", "systemctl", "reload", "caddy"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if reload_result.returncode == 0:
            result_msg = "Config loaded. Caddy will provision SSL certificates now."
        else:
            err = reload_result.stderr.strip()[:500]
            result_msg = f"Caddy reload failed: {err}"
    except PermissionError:
        result_msg = "Cannot write Caddyfile — permission denied."
    except Exception as e:
        result_msg = f"Caddy config error: {e}"

    # Store API token for DNS-01 providers (Caddy reads from env)
    if api_token and dns_provider:
        try:
            # Sanitize api_var and api_token to prevent escaping
            safe_api_var = (
                api_var.replace("\n", "").replace("\r", "").replace('"', "").replace("'", "")
            )
            safe_api_token = (
                api_token.replace("\n", "").replace("\r", "").replace('"', "").replace("'", "")
            )

            env_path = Path("/etc/caddy/.env")
            env_line = f"{safe_api_var}={safe_api_token}\n"
            if env_path.exists():
                content = env_path.read_text()
                if safe_api_var not in content:
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
    user = await get_admin(request, db)
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
            Path(CADDYFILE_PATH).read_text()[:2000] if Path(CADDYFILE_PATH).exists() else ""
        ),
        caddy_result=None,
    )

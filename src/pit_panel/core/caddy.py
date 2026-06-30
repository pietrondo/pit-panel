"""Caddy reverse proxy integration via admin API."""

import asyncio
import datetime as dt
import logging
import subprocess
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_last_ssl_renew_check: dt.datetime | None = None


async def ssl_auto_renew_loop():
    global _last_ssl_renew_check
    while True:
        await asyncio.sleep(21600)
        try:
            from pit_panel.config import get_settings

            settings = get_settings()
            caddy = CaddyManager(settings.caddy_admin_url)
            results = await caddy.auto_renew_certificates(
                getattr(settings, "ssl_auto_renew_days", 14)
            )
            _last_ssl_renew_check = dt.datetime.now(dt.UTC)
            if results:
                for r in results:
                    domain = r.get("domain", "?")
                    if r.get("success"):
                        logger.info(f"Auto-renewed certificate for {domain}")
                    else:
                        logger.warning(f"Auto-renew failed for {domain}: {r.get('error')}")
        except Exception:
            logger.exception("SSL auto-renew check failed")


def get_last_ssl_renew_check() -> dt.datetime | None:
    return _last_ssl_renew_check


class CaddyManager:
    def __init__(self, admin_url: str = "http://127.0.0.1:2019"):
        self.admin_url = admin_url.rstrip("/")

    async def add_subdomain(
        self, subdomain: str, base_domain: str, port: int = 80
    ) -> dict[str, Any]:
        fqdn = f"{subdomain}.{base_domain}"
        route = {
            "@id": fqdn,
            "match": [{"host": [fqdn]}],
            "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{port}"}]}],
        }
        return await self._patch_or_create_route(route)

    async def remove_subdomain(self, subdomain: str, base_domain: str) -> dict[str, Any]:
        fqdn = f"{subdomain}.{base_domain}"
        return await self._delete_route(fqdn)

    async def _patch_or_create_route(self, route: dict[str, Any]) -> dict[str, Any]:
        route_id = route["@id"]
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{self.admin_url}/id/{route_id}",
                json=route,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 404:
                resp2 = await client.post(
                    f"{self.admin_url}/config/apps/http/servers/srv0/routes/",
                    json=route,
                    headers={"Content-Type": "application/json"},
                )
                resp2.raise_for_status()
                return resp2.json() if resp2.text else {}
            resp.raise_for_status()
            return resp.json() if resp.text else {}

    async def setup_panel_route(
        self, panel_subdomain: str, base_domain: str, backend_port: int = 8080
    ) -> dict[str, Any]:
        fqdn = f"{panel_subdomain}.{base_domain}"
        route = {
            "@id": f"panel-{fqdn}",
            "match": [{"host": [fqdn]}],
            "handle": [
                {
                    "handler": "reverse_proxy",
                    "upstreams": [{"dial": f"127.0.0.1:{backend_port}"}],
                }
            ],
        }
        return await self._patch_or_create_route(route)

    async def add_main_domain(self, base_domain: str, port: int = 80) -> dict[str, Any]:
        route = {
            "@id": f"main-{base_domain}",
            "match": [{"host": [base_domain]}],
            "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{port}"}]}],
        }
        return await self._patch_or_create_route(route)

    async def remove_main_domain(self, base_domain: str) -> dict[str, Any]:
        return await self._delete_route(f"main-{base_domain}")

    async def get_certificates(self) -> list[dict[str, Any]]:
        domains = await self._get_managed_domains()
        if not domains:
            return []
        return self._check_certs_via_openssl(domains)

    async def _get_managed_domains(self) -> list[str]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.admin_url}/config/apps/http/servers", timeout=5)
                if resp.status_code != 200:
                    return []
                servers = resp.json() or {}
                domains = set()
                for srv in servers.values():
                    for route in srv.get("routes", []):
                        for match in route.get("match", []):
                            for host in match.get("host", []):
                                domains.add(host)
                return sorted(domains)
        except Exception as e:
            logger.warning(f"Failed to get managed domains from Caddy config: {e}")
            return []

    def _check_certs_via_openssl(self, domains: list[str]) -> list[dict[str, Any]]:
        certs = []
        for domain in domains:
            try:
                # 🛡️ Sentinel: Removed shell=True to prevent command injection
                r1 = subprocess.run(
                    ["openssl", "s_client", "-connect", "127.0.0.1:443", "-servername", domain],
                    input="\n",
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                r2 = subprocess.run(
                    ["openssl", "x509", "-noout", "-enddate", "-issuer"],
                    input=r1.stdout,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                not_after = ""
                issuer = ""
                for line in r2.stdout.split("\n"):
                    if line.startswith("notAfter="):
                        not_after = line.split("=", 1)[1].strip()
                    elif line.startswith("issuer="):
                        issuer = line.split("=", 1)[1].strip()
                if not not_after:
                    continue
                try:
                    cleaned = " ".join(not_after.rsplit(None, 1)[:-1])
                    expiry = dt.datetime.strptime(cleaned, "%b %d %H:%M:%S %Y")
                    days = (expiry.replace(tzinfo=dt.UTC) - dt.datetime.now(dt.UTC)).days
                except (ValueError, OSError):
                    days = None
                certs.append(
                    {
                        "serial": "?",
                        "domains": domain,
                        "not_before": "",
                        "not_after": not_after,
                        "expires_in_days": days,
                        "issuer": issuer or "Unknown",
                    }
                )
            except Exception:
                pass
        return certs

    async def renew_certificate(self, domain: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.admin_url}/config/",
                    timeout=5,
                )
                if resp.status_code == 200:
                    resp2 = await client.post(
                        f"{self.admin_url}/load",
                        json=resp.json(),
                        timeout=30,
                    )
                    resp2.raise_for_status()
                    return {
                        "success": True,
                        "domain": domain,
                        "note": "Config reloaded — Caddy will auto-renew",
                    }
                return {"success": False, "domain": domain, "error": "Cannot read config"}
            except Exception as e:
                logger.error(f"Failed to renew certificate for domain {domain}: {e}")
                return {"success": False, "domain": domain, "error": str(e)}

    async def auto_renew_certificates(self, renew_days: int = 14) -> list[dict[str, Any]]:
        results = []
        certs = await self.get_certificates()
        for cert in certs:
            days = cert.get("expires_in_days")
            if days is not None and days < renew_days:
                logger.info(f"Auto-renewing certificate for {cert['domains']} ({days} days left)")
                result = await self.renew_certificate(cert["domains"])
                results.append(result)
                if days is not None and days <= 7:
                    from pit_panel.core.notifier import notify_ssl_expiring
                    domains = (
                        cert["domains"].split(", ")
                        if isinstance(cert["domains"], str)
                        else [cert["domains"]]
                    )
                    await notify_ssl_expiring(domains, days)
        if not results:
            logger.info(f"Auto-renew: no certificates expiring within {renew_days} days")
        return results

    async def _delete_route(self, route_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self.admin_url}/id/{route_id}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}

    async def generate_and_reload(
        self, caddyfile_content: str, caddyfile_path: str = "/etc/caddy/Caddyfile"
    ) -> str:
        import os
        import tempfile

        # Validate the configuration using Caddy CLI first
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".validate", delete=False) as tmp:
                tmp.write(caddyfile_content)
                tmp_path = tmp.name

            process = await asyncio.create_subprocess_exec(
                "caddy",
                "validate",
                "--config",
                tmp_path,
                "--adapter",
                "caddyfile",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                err = (stderr.decode().strip() or stdout.decode().strip())[:500]
                return f"Caddy validation failed: {err}"
        except FileNotFoundError:
            # Caddy CLI not found in PATH (e.g. local dev), log warning and proceed
            logger.warning("Caddy CLI not found in PATH, skipping pre-flight validation")
        except Exception as e:
            logger.error(f"Error during Caddyfile pre-flight validation: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                import contextlib

                with contextlib.suppress(Exception):
                    os.unlink(tmp_path)

        try:
            Path(caddyfile_path).parent.mkdir(parents=True, exist_ok=True)
            Path(caddyfile_path).write_text(caddyfile_content)
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "-n",
                "systemctl",
                "reload",
                "caddy",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return "Config loaded. Caddy will provision SSL certificates now."
            else:
                err = stderr.decode().strip()[:500]
                return f"Caddy reload failed: {err}"
        except PermissionError:
            return "Cannot write Caddyfile — permission denied."
        except Exception as e:
            return f"Caddy config error: {e}"

    def save_api_token(
        self, api_var: str, api_token: str, env_path_str: str = "/etc/caddy/.env"
    ) -> str:
        from pathlib import Path

        try:
            safe_api_var = (
                api_var.replace("\n", "").replace("\r", "").replace('"', "").replace("'", "")
            )
            safe_api_token = (
                api_token.replace("\n", "").replace("\r", "").replace('"', "").replace("'", "")
            )

            env_path = Path(env_path_str)
            env_line = f"{safe_api_var}={safe_api_token}\n"
            if env_path.exists():
                content = env_path.read_text()
                if safe_api_var not in content:
                    env_path.write_text(content + env_line)
            else:
                env_path.write_text(env_line)
            return " API token saved."
        except (PermissionError, OSError):
            return " (API token not saved — set manually in /etc/caddy/.env)"

"""Caddy reverse proxy integration via admin API."""

import datetime as dt
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_PEM_CERT_PATTERN = re.compile(
    r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", re.DOTALL
)
_WHITESPACE_PATTERN = re.compile(r"\s+")
_DER_EXPIRY_PATTERN = re.compile(rb"\x17\x0d(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})Z")


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
        return await self._patch_routes(route)

    async def remove_subdomain(self, subdomain: str, base_domain: str) -> dict[str, Any]:
        fqdn = f"{subdomain}.{base_domain}"
        return await self._delete_route(fqdn)

    async def list_subdomains(self) -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.admin_url}/config/apps/http/servers/srv0/routes")
            routes = resp.json() or []
            return [r.get("@id", "") for r in routes if r.get("@id")]

    async def _patch_routes(self, route: dict[str, Any]) -> dict[str, Any]:
        route_id = route["@id"]
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{self.admin_url}/id/{route_id}",
                json=route,
                headers={"Content-Type": "application/json"},
            )
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
        return await self._patch_routes(route)

    async def add_main_domain(self, base_domain: str, port: int = 80) -> dict[str, Any]:
        route = {
            "@id": f"main-{base_domain}",
            "match": [{"host": [base_domain]}],
            "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{port}"}]}],
        }
        return await self._patch_routes(route)

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

    def _parse_cert(self, c: dict[str, Any]) -> dict[str, Any]:
        not_after = c.get("not_after", "")
        expires_in = None
        if not_after:
            try:
                expiry = dt.datetime.fromisoformat(not_after.replace("Z", "+00:00"))
                expires_in = (expiry - dt.datetime.now(dt.UTC)).days
            except (ValueError, TypeError):
                pass
        return {
            "serial": c.get("serial_number", "?")[:16],
            "domains": ", ".join(c.get("sans", []) or []),
            "not_before": c.get("not_before", ""),
            "not_after": not_after,
            "expires_in_days": expires_in,
            "issuer": c.get("issuer", {}).get("common_name", "?"),
        }

    def _parse_pem_certs(self, pem_text: str) -> list[dict[str, Any]]:
        import base64

        certs = []
        for match in _PEM_CERT_PATTERN.finditer(pem_text):
            try:
                der = base64.b64decode(_WHITESPACE_PATTERN.sub("", match.group(1)))
                na_match = _DER_EXPIRY_PATTERN.search(der)
                if na_match:
                    yy, mo, dd, hh, mm, ss = na_match.groups()
                    not_after = f"20{int(yy):02d}-{int(mo):02d}-{int(dd):02d}"
                    expiry = dt.datetime(
                        2000 + int(yy),
                        int(mo),
                        int(dd),
                        int(hh),
                        int(mm),
                        int(ss),
                        tzinfo=dt.UTC,
                    )
                    expires_in = (expiry - dt.datetime.now(dt.UTC)).days
                else:
                    not_after = "?"
                    expires_in = None
                certs.append(
                    {
                        "serial": match.group(1)[:16].strip(),
                        "domains": "Local CA",
                        "not_before": "",
                        "not_after": not_after,
                        "expires_in_days": expires_in,
                        "issuer": "Caddy Local CA",
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to parse PEM certificate: {e}")
        return certs

    def _parse_caddy_storage_certs(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        from pathlib import Path

        certs = []
        certs_paths = [
            "/var/lib/caddy/.local/share/caddy/certificates",
            "/home/caddy/.local/share/caddy/certificates",
            "/etc/caddy/.local/share/caddy/certificates",
        ]

        for certs_dir in certs_paths:
            dir_path = Path(certs_dir)
            try:
                json_files = list(dir_path.rglob("*.json"))
            except (PermissionError, Exception):
                try:
                    result = subprocess.run(
                        ["sudo", "-n", "find", certs_dir, "-name", "*.json"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    json_files = [Path(p) for p in result.stdout.strip().split("\n") if p]
                except Exception:
                    continue
            for json_file in json_files:
                try:
                    meta_text = self._read_file_safely(json_file)
                    if not meta_text:
                        continue
                    meta = json.loads(meta_text)
                    domains = meta.get("sans", meta.get("domains", [])) or []
                    if not domains:
                        continue

                    not_before = ""
                    not_after = ""
                    expires_in = None

                    pem_file = json_file.with_suffix(".crt")
                    if not pem_file.exists():
                        pem_file = json_file.with_suffix(".pem")
                    if not pem_file.exists():
                        pem_file = json_file.with_name(
                            json_file.stem.replace(".caddy-identifier", "") + ".crt"
                        )

                    if pem_file.exists():
                        try:
                            result = subprocess.run(
                                [
                                    "openssl",
                                    "x509",
                                    "-in",
                                    str(pem_file),
                                    "-noout",
                                    "-enddate",
                                    "-issuer",
                                ],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            for line in result.stdout.split("\n"):
                                if line.startswith("notAfter="):
                                    not_after = line.split("=", 1)[1]
                                elif line.startswith("notBefore="):
                                    not_before = line.split("=", 1)[1]
                            if not_after:
                                try:
                                    cleaned = " ".join(not_after.rsplit(None, 1)[:-1])
                                    expiry = dt.datetime.strptime(cleaned, "%b %d %H:%M:%S %Y")
                                    expires_in = (
                                        expiry.replace(tzinfo=dt.UTC) - dt.datetime.now(dt.UTC)
                                    ).days
                                except ValueError as e:
                                    logger.warning(f"Failed to parse expiry date: {e}")
                        except Exception as e:
                            logger.warning(f"Failed to execute openssl command: {e}")

                    if not not_after:
                        not_after = meta.get("not_after", "")

                    issuer = meta.get(
                        "issuer_common_name", meta.get("issuer_data", {}).get("ca", "Let's Encrypt")
                    )

                    certs.append(
                        {
                            "serial": str(meta.get("id", "?"))[:16],
                            "domains": ", ".join(domains),
                            "not_before": not_before if not_before else "",
                            "not_after": not_after if not_after else "",
                            "expires_in_days": expires_in,
                            "issuer": issuer,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse certificate metadata: {e}")
            if not certs:
                try:
                    if dir_path.is_dir():
                        certs = self._scan_via_openssl_client(certs_dir)
                except PermissionError:
                    pass
            if certs:
                break
        return certs

    def _read_file_safely(self, path: Path) -> str:
        try:
            return path.read_text()
        except PermissionError:
            try:
                result = subprocess.run(
                    ["sudo", "-n", "cat", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return result.stdout.strip() if result.returncode == 0 else ""
            except Exception:
                return ""

    def _find_pem_file(self, json_file: Path) -> Path | None:
        pem_file = json_file.with_suffix(".crt")
        if pem_file.exists():
            return pem_file
        pem_file = json_file.with_suffix(".pem")
        if pem_file.exists():
            return pem_file
        pem_file = json_file.with_name(json_file.stem.replace(".caddy-identifier", "") + ".crt")
        return pem_file if pem_file.exists() else None

    def _parse_expiry(self, pem_file: Path) -> tuple[str, int | None]:
        try:
            result = subprocess.run(
                ["openssl", "x509", "-in", str(pem_file), "-noout", "-enddate"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("notAfter="):
                    not_after = line.split("=", 1)[1]
                    try:
                        cleaned = " ".join(not_after.rsplit(None, 1)[:-1])
                        expiry = dt.datetime.strptime(cleaned, "%b %d %H:%M:%S %Y")
                        days = (expiry.replace(tzinfo=dt.UTC) - dt.datetime.now(dt.UTC)).days
                        return not_after, days
                    except ValueError as e:
                        logger.warning(f"Failed to parse expiry date: {e}")
        except Exception as e:
            logger.warning(f"Failed to execute openssl command: {e}")
        return "", None

    def _scan_via_openssl_client(self, certs_dir: str) -> list[dict[str, Any]]:
        certs = []
        try:
            for acme_dir in Path(certs_dir).iterdir():
                if not acme_dir.is_dir():
                    continue
                for domain_dir in acme_dir.iterdir():
                    if not domain_dir.is_dir():
                        continue
                    domain = domain_dir.name
                    try:
                        result = subprocess.run(
                            [
                                "openssl",
                                "s_client",
                                "-connect",
                                f"{domain}:443",
                                "-servername",
                                domain,
                            ],  # noqa: E501
                            input=b"\n",
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                    except Exception:
                        continue
                    for line in result.stdout.split("\n"):
                        if "NotAfter:" not in line:
                            continue
                        not_after = line.split("NotAfter:")[1].split(";")[0].strip()
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
                                "not_after": not_after[:10] if not_after else "",
                                "expires_in_days": days,
                                "issuer": "Let's Encrypt",
                            }
                        )
                        break
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

    async def _delete_route(self, route_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self.admin_url}/id/{route_id}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}

    async def generate_and_reload(
        self, caddyfile_content: str, caddyfile_path: str = "/etc/caddy/Caddyfile"
    ) -> str:
        import asyncio
        from pathlib import Path

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

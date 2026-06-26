"""Caddy reverse proxy integration via admin API."""

import datetime as dt
import re
import subprocess
from typing import Any

import httpx

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

    async def _patch_routes(self, route: dict) -> dict[str, Any]:
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

    async def get_certificates(self) -> list[dict[str, Any]]:
        certs = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.admin_url}/pki/ca/local/certificates",
                    headers={"Accept": "application/json"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    if resp.headers.get("content-type", "").startswith("application/json"):
                        for c in resp.json() or []:
                            certs.append(self._parse_cert(c))
                    else:
                        certs.extend(self._parse_pem_certs(resp.text))
            except Exception:
                pass

        if not certs:
            certs.extend(self._parse_caddy_storage_certs(client))
        else:
            certs.extend(self._parse_caddy_storage_certs(client))

        return certs

    def _parse_cert(self, c: dict) -> dict[str, Any]:
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
                der = base64.b64decode(
                    _WHITESPACE_PATTERN.sub("", match.group(1))
                )
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
            except Exception:
                pass
        return certs

    def _parse_caddy_storage_certs(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        import json
        from pathlib import Path

        certs = []
        certs_dir = Path("/var/lib/caddy/.local/share/caddy/certificates")

        try:
            for json_file in certs_dir.rglob("*.json"):
                try:
                    meta = json.loads(json_file.read_text())
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
                                    "-startdate",
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
                                    expiry = dt.datetime.strptime(
                                        not_after,
                                        "%b %d %H:%M:%S %Y %Z",
                                    )
                                    expires_in = (
                                        expiry.replace(tzinfo=dt.UTC) - dt.datetime.now(dt.UTC)
                                    ).days
                                except ValueError:
                                    pass
                        except Exception:
                            pass

                    if not not_after:
                        not_after = meta.get("not_after", "")
                        not_before = meta.get("not_before", "")

                    issuer = meta.get(
                        "issuer_common_name",
                        meta.get("issuer_data", {}).get("ca", "Let's Encrypt"),
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
                except Exception:
                    pass
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
                return {"success": False, "domain": domain, "error": str(e)}

    async def _delete_route(self, route_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self.admin_url}/id/{route_id}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}

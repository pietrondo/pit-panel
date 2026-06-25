"""Caddy reverse proxy integration via admin API."""

import datetime as dt
import re
from typing import Any

import httpx


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

        return certs

    def _parse_cert(self, c: dict) -> dict[str, Any]:
        not_after = c.get("not_after", "")
        expires_in = None
        if not_after:
            try:
                expiry = dt.datetime.fromisoformat(
                    not_after.replace("Z", "+00:00")
                )
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
        for match in re.finditer(
            r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----",
            pem_text,
            re.DOTALL,
        ):
            try:
                der = base64.b64decode(
                    re.sub(r"\s+", "", match.group(1))
                )
                na_match = re.search(
                    rb"\x17\x0d(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})Z",
                    der,
                )
                if na_match:
                    yy, mo, dd, hh, mm, ss = na_match.groups()
                    not_after = f"20{int(yy):02d}-{int(mo):02d}-{int(dd):02d}"
                    expiry = dt.datetime(
                        2000 + int(yy), int(mo), int(dd),
                        int(hh), int(mm), int(ss),
                        tzinfo=dt.UTC,
                    )
                    expires_in = (expiry - dt.datetime.now(dt.UTC)).days
                else:
                    not_after = "?"
                    expires_in = None
                certs.append({
                    "serial": match.group(1)[:16].strip(),
                    "domains": "Local CA",
                    "not_before": "",
                    "not_after": not_after,
                    "expires_in_days": expires_in,
                    "issuer": "Caddy Local CA",
                })
            except Exception:
                pass
        return certs

    def _parse_caddy_storage_certs(
        self, client: httpx.AsyncClient
    ) -> list[dict[str, Any]]:
        import json
        from pathlib import Path

        certs = []
        certs_dir = Path("/var/lib/caddy/.local/share/caddy/certificates")
        if certs_dir.exists():
            for meta_file in certs_dir.glob(
                "**/*.caddy-identifier.json"
            ):
                try:
                    meta = json.loads(meta_file.read_text())
                    certs.append({
                        "serial": meta.get("id", "?")[:16],
                        "domains": ", ".join(
                            meta.get("domains", []) or []
                        ),
                        "not_before": meta.get("not_before", ""),
                        "not_after": meta.get("not_after", ""),
                        "expires_in_days": None,
                        "issuer": meta.get(
                            "issuer", "Let's Encrypt"
                        ),
                    })
                except Exception:
                    pass
        return certs

    async def renew_certificate(self, domain: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.admin_url}/pki/ca/local/certificates?renew=true",
                    json={"sans": [domain]},
                    timeout=30,
                )
                resp.raise_for_status()
                return {"success": True, "domain": domain}
            except Exception as e:
                return {"success": False, "domain": domain, "error": str(e)}

    async def _delete_route(self, route_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self.admin_url}/id/{route_id}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}

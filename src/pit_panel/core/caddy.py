from typing import Any
"""Caddy reverse proxy integration via admin API."""

import datetime as dt

import httpx


class CaddyManager:
    def __init__(self, admin_url: str = "http://127.0.0.1:2019"):
        self.admin_url = admin_url.rstrip("/")

    async def add_subdomain(self, subdomain: str, base_domain: str, port: int = 80) -> dict[str, Any]:
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

    async def get_certificates(self) -> list[dict[str, Any]]:
        certs = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.admin_url}/pki/ca/local/certificates", timeout=5)
                if resp.status_code == 200:
                    for c in resp.json() or []:
                        not_after = c.get("not_after", "")
                        expires_in = None
                        if not_after:
                            try:
                                expiry = dt.datetime.fromisoformat(not_after.replace("Z", "+00:00"))
                                expires_in = (expiry - dt.datetime.now(dt.UTC)).days
                            except (ValueError, TypeError):
                                pass
                        certs.append(
                            {
                                "serial": c.get("serial_number", "?")[:16],
                                "domains": ", ".join(c.get("sans", []) or []),
                                "not_before": c.get("not_before", ""),
                                "not_after": not_after,
                                "expires_in_days": expires_in,
                                "issuer": c.get("issuer", {}).get("common_name", "?"),
                            }
                        )
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

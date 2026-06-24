"""Caddy reverse proxy integration via admin API."""


import httpx


class CaddyManager:
    def __init__(self, admin_url: str = "http://127.0.0.1:2019"):
        self.admin_url = admin_url.rstrip("/")

    async def add_subdomain(self, subdomain: str, base_domain: str, port: int = 80) -> dict:
        fqdn = f"{subdomain}.{base_domain}"
        route = {
            "@id": fqdn,
            "match": [{"host": [fqdn]}],
            "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{port}"}]}],
        }
        return await self._patch_routes(route)

    async def remove_subdomain(self, subdomain: str, base_domain: str) -> dict:
        fqdn = f"{subdomain}.{base_domain}"
        return await self._delete_route(fqdn)

    async def list_subdomains(self) -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.admin_url}/config/apps/http/servers/srv0/routes")
            routes = resp.json() or []
            return [r.get("@id", "") for r in routes if r.get("@id")]

    async def _patch_routes(self, route: dict) -> dict:
        route_id = route["@id"]
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{self.admin_url}/id/{route_id}",
                json=route,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json() if resp.text else {}

    async def _delete_route(self, route_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self.admin_url}/id/{route_id}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}

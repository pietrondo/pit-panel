"""Is the domain we hand to customers actually delegated in public DNS?

A Dynu root that is not delegated answers nothing: every record created under
it exists only inside Dynu, so the URL given to a customer never resolves. The
panel used to accept such a root silently.
"""

from __future__ import annotations

import time

import httpx

_CACHE: dict[str, tuple[float, list[str] | None]] = {}
_TTL_SECONDS = 300
_DOH_URL = "https://cloudflare-dns.com/dns-query"


async def name_servers(domain: str) -> list[str] | None:
    """NS records of ``domain``, or None when the lookup itself failed."""
    cached = _CACHE.get(domain)
    if cached and time.monotonic() - cached[0] < _TTL_SECONDS:
        return cached[1]

    servers: list[str] | None
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(
                _DOH_URL,
                params={"name": domain, "type": "NS"},
                headers={"Accept": "application/dns-json"},
            )
            response.raise_for_status()
            answers = response.json().get("Answer") or []
        servers = [str(a["data"]) for a in answers if a.get("type") == 2]
    except Exception:
        return None

    _CACHE[domain] = (time.monotonic(), servers)
    return servers


async def root_problem(domain: str) -> str | None:
    """A sentence for the operator when subdomains under ``domain`` cannot resolve."""
    if not domain:
        return None
    servers = await name_servers(domain)
    if servers is None:
        return None
    if not servers:
        return (
            f"{domain} has no NS records in public DNS: no subdomain under it will "
            f"resolve. Check that the domain is active in Dynu and its nameservers "
            f"are delegated."
        )
    return None

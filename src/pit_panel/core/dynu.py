"""Dynu v2 DNS API client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


class DynuError(RuntimeError):
    """Raised when Dynu cannot complete a DNS operation."""


class DynuClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.dynu.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise DynuError("Dynu API key is not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "API-Key": api_key,
            },
            timeout=10.0,
            transport=transport,
        )

    async def __aenter__(self) -> DynuClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _domain_id(self, domain: str) -> int:
        response = await self._client.get("/v2/dns")
        self._raise(response)
        for item in response.json():
            if str(item.get("name", "")).rstrip(".").lower() == domain.rstrip(".").lower():
                return int(item["id"])
        raise DynuError(f"Dynu domain not found: {domain}")

    async def list_domains(self) -> list[str]:
        """Root hostnames this account can create records under."""
        response = await self._client.get("/v2/dns")
        self._raise(response)
        names = []
        for item in response.json():
            name = str(item.get("name", "")).rstrip(".")
            if name:
                names.append(name)
        return names

    async def add_a_record(self, domain: str, node: str, ipv4: str) -> dict[str, Any]:
        domain_id, records = await self._records(domain)
        for record in records:
            if record.get("nodeName") == node and record.get("recordType") in {"A", "CNAME"}:
                raise DynuError(f"Dynu record already exists for {node}.{domain}")
        response = await self._client.post(
            f"/v2/dns/{domain_id}/record",
            json={
                "nodeName": node,
                "recordType": "A",
                "ipv4Address": ipv4,
                "ttl": 300,
                "state": True,
            },
        )
        self._raise(response)
        return response.json()

    async def _records(self, domain: str) -> tuple[int, list[dict[str, Any]]]:
        domain_id = await self._domain_id(domain)
        response = await self._client.get(f"/v2/dns/{domain_id}/record")
        self._raise(response)
        return domain_id, response.json()

    async def delete_record(self, domain: str, record_id: int) -> None:
        domain_id = await self._domain_id(domain)
        response = await self._client.delete(f"/v2/dns/{domain_id}/record/{record_id}")
        self._raise(response)

    async def delete_a_record(self, domain: str, node: str) -> None:
        domain_id, records = await self._records(domain)
        for record in records:
            if record.get("nodeName") == node and record.get("recordType") == "A":
                await self.delete_record(domain, int(record["id"]))
                return

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_error:
            detail = response.text[:300]
            raise DynuError(f"Dynu API request failed ({response.status_code}): {detail}")


_ROOTS_CACHE: dict[str, tuple[float, DynuRoots]] = {}
_ROOTS_TTL_SECONDS = 300


@dataclass(frozen=True)
class DynuRoots:
    """What the Dynu account can serve, and why when it cannot be read.

    ``roots`` is None when the question could not be answered (no key, Dynu
    unreachable, key rejected). That is never the same as "no domains".
    """

    roots: list[str] | None
    error: str | None = None


async def available_roots(settings: Any) -> DynuRoots:
    """Root hostnames the Dynu account can serve."""
    key = getattr(settings, "dynu_api_key", "")
    if not isinstance(key, str) or not key.strip():
        return DynuRoots(None, "No Dynu API key saved")

    cached = _ROOTS_CACHE.get(key)
    if cached and time.monotonic() - cached[0] < _ROOTS_TTL_SECONDS:
        return cached[1]

    try:
        async with DynuClient(key) as client:
            result = DynuRoots(await client.list_domains())
    except DynuError as exc:
        result = DynuRoots(None, str(exc))
    except Exception as exc:
        result = DynuRoots(None, f"Dynu unreachable: {exc}")

    _ROOTS_CACHE[key] = (time.monotonic(), result)
    return result

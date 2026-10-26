"""Dynu v2 DNS API client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


class DynuError(RuntimeError):
    """Raised when Dynu cannot complete a DNS operation."""


def _envelope_items(payload: Any, key: str) -> list[dict[str, Any]]:
    """Records of a Dynu list response, with or without its envelope.

    The documented shape is ``{"statusCode": 200, "<key>": [...]}``. A bare list
    is accepted too, and when the key is not the documented one the first list
    of objects in the envelope is used, so a rename on their side does not take
    the panel down.
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        for value in payload.values():
            if isinstance(value, list) and any(isinstance(item, dict) for item in value):
                return [item for item in value if isinstance(item, dict)]
        # Nothing list-shaped: say what came back instead of pretending it is empty.
        raise DynuError(
            f"Dynu answered without {key}: keys={sorted(str(k) for k in payload)[:8]}"
        )

    raise DynuError(f"Dynu answered with {type(payload).__name__}, expected a list")


def _created_record(payload: Any) -> dict[str, Any]:
    """The record object of a create response, wherever Dynu put it."""
    if isinstance(payload, dict):
        if "id" in payload:
            return payload
        candidates: list[Any] = list(payload.values())
    elif isinstance(payload, list):
        candidates = payload
    else:
        return {}

    for value in candidates:
        if isinstance(value, dict) and "id" in value:
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "id" in item:
                    return item
    return {}


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

    async def _domains(self) -> list[dict[str, Any]]:
        """The domains of the account.

        Dynu wraps its lists in an envelope (``{"statusCode": 200, "domains":
        [...]}``), so iterating the decoded body directly yields the envelope's
        keys instead of the records. Both shapes are accepted here.
        """
        response = await self._client.get("/v2/dns")
        self._raise(response)
        return _envelope_items(response.json(), "domains")

    async def _domain_id(self, domain: str) -> int:
        for item in await self._domains():
            if str(item.get("name", "")).rstrip(".").lower() == domain.rstrip(".").lower():
                return int(item["id"])
        raise DynuError(f"Dynu domain not found: {domain}")

    async def list_domains(self) -> list[str]:
        """Root hostnames this account can create records under."""
        names = []
        for item in await self._domains():
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
        record = _created_record(response.json())
        if not record:
            raise DynuError(f"Dynu did not return the created record for {node}.{domain}")
        return record

    async def _records(self, domain: str) -> tuple[int, list[dict[str, Any]]]:
        domain_id = await self._domain_id(domain)
        response = await self._client.get(f"/v2/dns/{domain_id}/record")
        self._raise(response)
        return domain_id, _envelope_items(response.json(), "dnsRecords")

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

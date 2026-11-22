"""Health check helper used by the post-update verifier."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def check_post_update(
    base_url: str = "http://127.0.0.1:8080",
    retries: int = 30,
    delay: float = 2.0,
) -> bool:
    async with httpx.AsyncClient() as client:
        for _ in range(retries):
            try:
                resp = await client.get(f"{base_url}/health", timeout=5)
                if resp.status_code == 200:
                    return True
            except Exception as e:
                logger.warning("Health check error: %s", e)
            await asyncio.sleep(delay)
    return False

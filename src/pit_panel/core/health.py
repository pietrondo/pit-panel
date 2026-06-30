"""Health check endpoint helpers."""

import asyncio
import datetime
import logging

import httpx

logger = logging.getLogger(__name__)

async def check_post_update(base_url: str = "http://127.0.0.1:8080") -> bool:
    deadline = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=60)
    async with httpx.AsyncClient() as client:
        while datetime.datetime.now(datetime.UTC) < deadline:
            try:
                resp = await client.get(f"{base_url}/health", timeout=5)
                if resp.status_code == 200:
                    return True
            except Exception as e:
                logger.warning("Health check error: %s", e)
            await asyncio.sleep(2)
    return False

"""Health check endpoint helpers + container health monitor."""

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


async def docker_health_monitor_loop() -> None:
    import logging

    logger = logging.getLogger(__name__)
    from pit_panel.core.docker_ops import DockerManager
    from pit_panel.core.notifier import notify_system_alarm

    manager = DockerManager()
    while True:
        try:
            containers = await manager.ps_all()
            for c in containers:
                state = str(c.get("State", "")).lower()
                status = str(c.get("Status", "")).lower()
                is_crashed = state == "exited" and "exited (0)" not in status or state == "dead"
                if not is_crashed:
                    continue
                cid = c.get("ID", "")
                name = c.get("Names", cid)
                logger.warning("Container %s crashed, restarting...", name)
                res = await manager.container_start(cid)
                if res.get("success"):
                    await notify_system_alarm(
                        "Container Restarted",
                        f"Container <b>{name}</b> was crashed and has been restarted.",
                    )
                else:
                    await notify_system_alarm(
                        "Container Restart Failed",
                        f"Container <b>{name}</b> crashed, restart failed: {res.get('error', '?')}",
                    )
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("docker_health_monitor_loop error: %s", e)
            await asyncio.sleep(60)

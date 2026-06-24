"""Self-update mechanism with healthcheck and rollback."""

import asyncio
import datetime
import subprocess

import httpx

from pit_panel.config import Settings
from pit_panel.db.models import UpdateHistory
from pit_panel.db.session import get_sessionmaker


class Updater:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def check_for_updates(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "fetch", "origin", self.settings.git_branch],
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/opt/pit-panel",
            )
            result = subprocess.run(
                ["git", "rev-parse", f"origin/{self.settings.git_branch}"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd="/opt/pit-panel",
            )
            remote_sha = result.stdout.strip()

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd="/opt/pit-panel",
            )
            local_sha = result.stdout.strip()

            if remote_sha != local_sha:
                return remote_sha
            return None
        except Exception:
            return None

    async def apply_update(self, target_sha: str) -> bool:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            current = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd="/opt/pit-panel",
            ).stdout.strip()

            entry = UpdateHistory(
                version_from=current[:8],
                version_to=target_sha[:8],
                status="started",
            )
            db.add(entry)
            await db.commit()

            subprocess.run(
                ["git", "reset", "--hard", target_sha],
                capture_output=True,
                timeout=30,
                cwd="/opt/pit-panel",
            )
            subprocess.run(
                ["uv", "sync"],
                capture_output=True,
                timeout=120,
                cwd="/opt/pit-panel",
            )
            subprocess.run(
                ["uv", "run", "alembic", "upgrade", "head"],
                capture_output=True,
                timeout=60,
                cwd="/opt/pit-panel",
            )

            entry.status = "completed"
            entry.completed_at = datetime.datetime.now(datetime.UTC)
            await db.commit()
            return True

    async def rollback(self) -> bool:
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            capture_output=True,
            timeout=10,
            cwd="/opt/pit-panel",
        )
        subprocess.run(
            ["uv", "sync"],
            capture_output=True,
            timeout=120,
            cwd="/opt/pit-panel",
        )
        return True

    async def healthcheck(
        self,
        url: str = "http://127.0.0.1:8080/health",
        retries: int = 30,
        delay: float = 2.0,
    ) -> bool:
        async with httpx.AsyncClient() as client:
            for _ in range(retries):
                try:
                    resp = await client.get(url, timeout=5)
                    if resp.status_code == 200:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(delay)
        return False

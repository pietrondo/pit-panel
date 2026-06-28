"""Self-update mechanism with healthcheck and rollback."""

import asyncio
import contextlib
import datetime
from dataclasses import dataclass

import httpx

from pit_panel.config import Settings
from pit_panel.db.models import UpdateHistory
from pit_panel.db.session import get_sessionmaker


@dataclass
class _CmdResult:
    returncode: int
    stdout: str
    stderr: str


async def _run_cmd(cmd: list[str], timeout: int, cwd: str | None = None) -> _CmdResult:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return _CmdResult(
            returncode=proc.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )
    except TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return _CmdResult(returncode=-1, stdout="", stderr="Timeout")
    except Exception as e:
        return _CmdResult(returncode=-1, stdout="", stderr=str(e))


class Updater:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def check_for_updates(self) -> str | None:
        try:
            result = await _run_cmd(
                [
                    "sudo",
                    "-n",
                    "git",
                    "-C",
                    "/opt/pit-panel",
                    "fetch",
                    "origin",
                    self.settings.git_branch,
                ],
                timeout=30,
            )
            if result.returncode != 0:
                return None
            result = await _run_cmd(
                ["git", "rev-parse", f"origin/{self.settings.git_branch}"],
                timeout=10,
                cwd="/opt/pit-panel",
            )
            remote_sha = result.stdout.strip()
            if not remote_sha:
                return None

            result = await _run_cmd(
                ["git", "rev-parse", "HEAD"],
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
            current_result = await _run_cmd(
                ["git", "rev-parse", "HEAD"],
                timeout=10,
                cwd="/opt/pit-panel",
            )
            current = current_result.stdout.strip()

            entry = UpdateHistory(
                version_from=current[:8] if current else "?",
                version_to=target_sha[:8],
                status="started",
            )
            db.add(entry)
            await db.commit()

            steps = [
                (["sudo", "-n", "git", "-C", "/opt/pit-panel", "reset", "--hard", target_sha], 30),
                (["sudo", "-n", "uv", "--directory", "/opt/pit-panel", "sync"], 120),
                (["uv", "run", "alembic", "upgrade", "head"], 60),
            ]
            for cmd, timeout in steps:
                result = await _run_cmd(
                    cmd,
                    timeout=timeout,
                    cwd="/opt/pit-panel",
                )
                if result.returncode != 0:
                    entry.status = "failed"
                    entry.completed_at = datetime.datetime.now(datetime.UTC)
                    await db.commit()
                    return False

            entry.status = "completed"
            entry.completed_at = datetime.datetime.now(datetime.UTC)
            await db.commit()
            return True

    async def rollback(self) -> bool:
        result = await _run_cmd(
            ["sudo", "-n", "git", "-C", "/opt/pit-panel", "reset", "--hard", "HEAD~1"],
            timeout=10,
        )
        if result.returncode != 0:
            return False
        result = await _run_cmd(
            ["sudo", "-n", "uv", "--directory", "/opt/pit-panel", "sync"],
            timeout=120,
        )
        return result.returncode == 0

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

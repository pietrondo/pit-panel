"""Docker Compose operations wrapper."""

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any


class DockerManager:
    def __init__(self, apps_dir: str = "/opt/pit-panel/apps"):
        self.apps_dir = Path(apps_dir)

    async def _run_compose(self, command: list[str], subdomain: str) -> dict[str, Any]:
        path = self.apps_dir / subdomain
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            str(path / "docker-compose.yml"),
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(path),
        )
        stdout, stderr = await proc.communicate()
        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    async def compose_up(self, subdomain: str) -> dict[str, Any]:
        return await self._run_compose(["up", "-d"], subdomain)

    async def compose_down(self, subdomain: str) -> dict[str, Any]:
        return await self._run_compose(["down"], subdomain)

    async def compose_ps(self, subdomain: str) -> list[dict[str, Any]]:
        path = self.apps_dir / subdomain
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            str(path / "docker-compose.yml"),
            "ps",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(path),
        )
        stdout, _ = await proc.communicate()
        containers = []
        for line in stdout.decode().strip().split("\n"):
            if line.strip():
                with contextlib.suppress(json.JSONDecodeError):
                    containers.append(json.loads(line))
        return containers

    async def compose_logs(self, subdomain: str, tail: int = 100) -> str:
        path = self.apps_dir / subdomain
        args = [
            "docker",
            "compose",
            "-f",
            str(path / "docker-compose.yml"),
            "logs",
            "--tail",
            str(tail),
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(path),
        )
        stdout, _ = await proc.communicate()
        return stdout.decode()

    async def compose_restart(self, subdomain: str) -> dict[str, Any]:
        return await self._run_compose(["restart"], subdomain)

    async def ps_all(self) -> list[dict[str, Any]]:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "-a",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        containers = []
        for line in stdout.decode().strip().split("\n"):
            if line.strip():
                with contextlib.suppress(json.JSONDecodeError):
                    containers.append(json.loads(line))
        return containers

    async def container_stop(self, container_id: str) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "stop",
            container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    async def container_start(self, container_id: str) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "start",
            container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    async def container_stats(self, container_id: str) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "stats",
            container_id,
            "--no-stream",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            return json.loads(stdout.decode().strip())
        except json.JSONDecodeError:
            return {}

    async def container_logs_live(self, container_id: str, tail: int = 100) -> str:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "logs",
            container_id,
            "--tail",
            str(tail),
            "--timestamps",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode()
        if stderr:
            output += "\n" + stderr.decode()
        return output

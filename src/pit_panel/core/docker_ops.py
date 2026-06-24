"""Docker Compose operations wrapper."""

import asyncio
import contextlib
import json
from pathlib import Path


class DockerManager:
    def __init__(self, apps_dir: str = "/opt/pit-panel/apps"):
        self.apps_dir = Path(apps_dir)

    async def compose_up(self, subdomain: str) -> dict:
        path = self.apps_dir / subdomain
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", str(path / "docker-compose.yml"), "up", "-d",
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

    async def compose_down(self, subdomain: str) -> dict:
        path = self.apps_dir / subdomain
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", str(path / "docker-compose.yml"), "down",
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

    async def compose_ps(self, subdomain: str) -> list[dict]:
        path = self.apps_dir / subdomain
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", str(path / "docker-compose.yml"), "ps", "--format", "json",
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
            "docker", "compose", "-f",
            str(path / "docker-compose.yml"),
            "logs", "--tail", str(tail),
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(path),
        )
        stdout, _ = await proc.communicate()
        return stdout.decode()

    async def compose_restart(self, subdomain: str) -> dict:
        path = self.apps_dir / subdomain
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", str(path / "docker-compose.yml"), "restart",
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

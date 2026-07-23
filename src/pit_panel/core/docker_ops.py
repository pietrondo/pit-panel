"""Docker Compose operations wrapper."""

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any, cast


class DockerManager:
    def __init__(self, apps_dir: str = "/opt/pit-panel/apps"):
        self.apps_dir = Path(apps_dir)

    async def run_compose_command(self, subdomain: str, command: list[str]) -> dict[str, Any]:
        path = self.apps_dir / subdomain
        try:
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
        except OSError as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "error": f"Failed to execute docker compose command: {e}",
            }

    async def exec_command(
        self,
        subdomain: str,
        service: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        path = self.apps_dir / subdomain
        env_args = []
        if env:
            for k, v in env.items():
                env_args.extend(["-e", f"{k}={v}"])
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "compose",
                "-f",
                str(path / "docker-compose.yml"),
                "exec",
                "-T",
                *env_args,
                service,
                *cmd,
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
        except OSError as e:
            return {"success": False, "stdout": "", "stderr": str(e)}

    async def compose_ps(self, subdomain: str) -> list[dict[str, Any]]:
        path = self.apps_dir / subdomain
        try:
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
        except OSError:
            return []

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
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(path),
            )
            stdout, _ = await proc.communicate()
            return stdout.decode()
        except OSError as e:
            return f"Failed to retrieve logs: {e}"

    _containers_cache: tuple[float, tuple[int, int]] | None = None
    _cache_apps_dir: str = ""

    async def containers_count(self) -> tuple[int, int]:
        now = time.monotonic()
        if DockerManager._containers_cache is not None:
            cached_at, value = DockerManager._containers_cache
            if now - cached_at < 5 and DockerManager._cache_apps_dir == str(self.apps_dir):
                return value
        containers = await self.ps_all()
        total = len(containers)
        running = sum(1 for c in containers if c.get("State") == "running")
        DockerManager._containers_cache = (now, (total, running))
        DockerManager._cache_apps_dir = str(self.apps_dir)
        return total, running

    async def ps_all(self) -> list[dict[str, Any]]:
        try:
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
        except OSError:
            return []

    async def stats_all(self) -> dict[str, dict[str, Any]]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            result: dict[str, dict[str, Any]] = {}
            for line in stdout.decode().strip().split("\n"):
                if line.strip():
                    with contextlib.suppress(json.JSONDecodeError):
                        entry = json.loads(line)
                        name = entry.get("Name", "")
                        if name:
                            result[name] = entry
            return result
        except OSError:
            return {}

    async def container_stop(self, container_id: str) -> dict[str, Any]:
        try:
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
        except OSError as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "error": f"Failed to stop container: {e}",
            }

    async def container_start(self, container_id: str) -> dict[str, Any]:
        try:
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
        except OSError as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "error": f"Failed to start container: {e}",
            }

    async def container_stats(self, container_id: str) -> dict[str, Any]:
        try:
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
                return cast(dict[str, Any], json.loads(stdout.decode().strip()))
            except json.JSONDecodeError:
                return {}
        except OSError:
            return {}

    async def container_logs_live(self, container_id: str, tail: int = 100) -> str:
        try:
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
        except OSError as e:
            return f"Failed to retrieve container logs: {e}"

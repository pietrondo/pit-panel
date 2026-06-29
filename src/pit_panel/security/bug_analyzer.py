"""Software Bug and Error Analysis Tool."""

import asyncio
import re
from typing import Any


async def analyze_container_logs() -> list[dict[str, Any]]:
    """Scan running Docker containers for common software exceptions and errors."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "--format",
            "{{.ID}}|{{.Names}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []

        bugs = []
        # Patterns for common software bugs and errors
        error_patterns = [
            re.compile(r"(?i)exception"),
            re.compile(r"(?i)traceback"),
            re.compile(r"(?i)fatal\s+error"),
            re.compile(r"(?i)panic:"),
            re.compile(r"(?i)syntaxerror"),
            re.compile(r"(?i)referenceerror"),
            re.compile(r"(?i)typeerror"),
            re.compile(r"(?i)unhandled\s+promise"),
            re.compile(r"(?i)segmentation\s+fault"),
        ]

        for line in stdout.decode().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 1)
            if len(parts) != 2:
                continue
            cid, name = parts

            # Skip security tools
            if "clamav" in name:
                continue

            log_proc = await asyncio.create_subprocess_exec(
                "docker",
                "logs",
                "--tail",
                "500",
                cid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                l_stdout, l_stderr = await asyncio.wait_for(log_proc.communicate(), timeout=5)
            except TimeoutError:
                log_proc.kill()
                continue

            logs = l_stdout.decode(errors="replace") + "\n" + l_stderr.decode(errors="replace")

            container_bugs = []
            for log_line in logs.split("\n"):
                if any(p.search(log_line) for p in error_patterns):
                    container_bugs.append(log_line.strip()[:250])

            if container_bugs:
                unique_bugs = list(set(container_bugs))[:10]
                bugs.append(
                    {"container": name, "errors": unique_bugs, "count": len(container_bugs)}
                )

        return bugs
    except Exception:
        return []


async def analyze_system_logs() -> list[str]:
    """Scan system logs (journalctl) for Pit Panel errors."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "journalctl",
            "-u",
            "pit-panel",
            "-n",
            "500",
            "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []

        logs = stdout.decode(errors="replace")

        errors = []
        for line in logs.split("\n"):
            if "ERROR" in line or "CRITICAL" in line or "Exception" in line:
                # Strip timestamp prefix if possible to keep it clean
                clean_line = re.sub(r"^.*?pit-panel\[\d+\]:\s*", "", line)
                errors.append(clean_line.strip()[:200])

        return list(set(errors))[:15]
    except Exception:
        return []

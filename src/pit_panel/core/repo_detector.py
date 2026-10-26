"""GitHub repository analysis for automatic stack detection."""

import asyncio
import logging
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from pit_panel.core.repo_validator import isolated_git_env, validate_repository_url_async

logger = logging.getLogger(__name__)


async def _terminate_kill_and_drain(proc) -> None:
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
    except BaseException:
        with suppress(ProcessLookupError):
            proc.kill()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except BaseException:
        with suppress(ProcessLookupError):
            proc.kill()
        with suppress(BaseException):
            await asyncio.wait_for(proc.wait(), timeout=5)
    if isinstance(proc, asyncio.subprocess.Process):
        with suppress(BaseException):
            await asyncio.wait_for(proc.communicate(), timeout=5)


@dataclass
class DetectedStack:
    stack_type: str
    display_name: str
    confidence: int
    indicators: list[str] = field(default_factory=list)


async def analyze_repo(repo_url: str) -> DetectedStack:
    repo_path = await clone_repo(repo_url)
    try:
        return detect_stack(repo_path)
    finally:
        cleanup(repo_path)


async def clone_repo(repo_url: str) -> Path:
    if not await validate_repository_url_async(repo_url):
        raise ValueError("Invalid or disallowed repository URL.")

    dest = Path(tempfile.mkdtemp(prefix="pit-panel-repo-"))
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            "http.followRedirects=false",
            "clone",
            "--depth",
            "1",
            "--",
            repo_url,
            str(dest),
            env=isolated_git_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            raise ValueError(f"Git clone failed: {stderr.decode(errors='replace')[:500]}")
    except BaseException as e:
        try:
            if proc is not None and proc.returncode is None:
                await _terminate_kill_and_drain(proc)
        finally:
            cleanup(dest)
        if isinstance(e, TimeoutError):
            raise ValueError(f"Git clone timed out for repository: {repo_url}") from e
        if isinstance(e, OSError):
            raise ValueError(f"Git executable not found or inaccessible: {e}") from e
        raise
    return dest


def detect_stack(repo_path: Path) -> DetectedStack:
    files = {f.name for f in repo_path.iterdir() if f.is_file()}
    dirs = {d.name for d in repo_path.iterdir() if d.is_dir()}

    if "wp-config.php" in files or "wp-content" in dirs:
        return DetectedStack("wordpress", "WordPress", 95, ["wp-config.php / wp-content/"])

    if "Ghostfile" in files or any(d.startswith("ghost") for d in dirs):
        return DetectedStack("ghost", "Ghost", 90, ["Ghostfile or ghost directory"])

    has_package = "package.json" in files
    if has_package:
        has_next = bool({"next.config.js", "next.config.mjs", "next.config.ts"} & files)
        if has_next:
            return DetectedStack("nextjs", "Next.js", 95, ["package.json", "next.config.*"])
        has_vite = bool({"vite.config.ts", "vite.config.js", "vite.config.mjs"} & files)
        confidence = 95 if has_vite else 85
        indicators = ["package.json"]
        if has_vite:
            indicators.append("vite.config.*")
        return DetectedStack("nodejs", "Node.js", confidence, indicators)

    has_req = bool({"requirements.txt", "Pipfile", "pyproject.toml", "setup.py"} & files)
    if has_req:
        for fname in ("main.py", "app.py"):
            fpath = repo_path / fname
            if fpath.is_file():
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                if "FastAPI" in content:
                    return DetectedStack(
                        "python-fastapi", "Python FastAPI", 95, ["requirements.txt", fname]
                    )
                if "Flask" in content:
                    return DetectedStack(
                        "python-flask", "Python Flask", 95, ["requirements.txt", fname]
                    )
        return DetectedStack("python-flask", "Python", 80, ["requirements.txt"])

    if "index.html" in files:
        return DetectedStack("static-nginx", "Static Site", 90, ["index.html"])

    if "Dockerfile" in files:
        return DetectedStack("custom-compose", "Docker (custom)", 70, ["Dockerfile"])

    return DetectedStack("custom-compose", "Custom", 30, ["unknown stack"])


def cleanup(repo_path: Path) -> None:
    try:
        shutil.rmtree(repo_path)
    except Exception as e:
        logger.warning(f"Failed to cleanup {repo_path}: {e}")

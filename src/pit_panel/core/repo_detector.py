"""GitHub repository analysis for automatic stack detection."""

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


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
    import re
    if repo_url.startswith("-"):
        raise ValueError("Invalid repository URL format.")
    if not re.match(r"^(https?|git)://[a-zA-Z0-9.-]+", repo_url):
        raise ValueError("Invalid repository URL format.")

    dest = Path(tempfile.mkdtemp(prefix="pit-panel-repo-"))
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            "--",
            repo_url,
            str(dest),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            raise ValueError(f"Git clone failed: {stderr.decode(errors='replace')[:500]}")
    except TimeoutError as e:
        raise ValueError(f"Git clone timed out for repository: {repo_url}") from e
    except OSError as e:
        raise ValueError(f"Git executable not found or inaccessible: {e}") from e
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
        return DetectedStack("nodejs", "Node.js", 85, ["package.json"])

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
        shutil.rmtree(repo_path, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup {repo_path}: {e}")

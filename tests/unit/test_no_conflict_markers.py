"""Guard test: fail if any unresolved git merge conflict markers remain in the
repository working tree.

Git conflict markers have the following line-start signatures:

    <<<<<<<  (7+ less-than signs)
    >>>>>>>  (7+ greater-than signs)
    =======  (7+ equals signs)
    |||||||  (7+ pipes)

These should never survive into a committed file.  This test walks every
tracked and untracked file (excluding standard noise directories) and asserts
that no such markers exist, failing with a precise file:line listing so the
offender can be removed immediately.
"""

import os
import re
import subprocess

import pytest

# Regex matching the four conflict-marker prefixes at the start of a line,
# optionally followed by a space (as git writes them) or end-of-line.
_CONFLICT_MARKER_RE = re.compile(r"^(<{7}|\|{7}|={7}|>{7})( |$)")

# Directories that are standard build / dependency / cache artefacts and should
# never be scanned for conflict markers.
_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".venv",
    ".venv-build",
    "__pycache__",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".cache",
    ".jules",
}


def _repo_root() -> str:
    """Return the git repository root for the current working directory."""
    return subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()


def _find_conflict_markers(root: str) -> list[tuple[str, int, str]]:
    """Walk *root* recursively and return ``[(file, line_no, line), ...]`` for
    every line containing a git conflict marker.

    Files inside :data:`_EXCLUDE_DIRS` or with unknown binary extensions are
    skipped.
    """
    offenders: list[tuple[str, int, str]] = []

    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    tracked_files = [f for f in result.stdout.splitlines() if f]

    for rel_path in tracked_files:
        # Skip anything inside an excluded directory.
        parts = rel_path.replace("\\", "/").split("/")
        if any(part in _EXCLUDE_DIRS for part in parts):
            continue

        # os.path.join, non f-string + replace: costruito a mano il path
        # risulta sbagliato su Linux, dove il path del repo non e' un prefisso
        # Windows, e ogni file verrebbe silenziosamente saltato.
        abs_path = os.path.join(root, rel_path)
        try:
            with open(abs_path, encoding="utf-8", errors="ignore") as fh:
                for line_no, line in enumerate(fh, start=1):
                    if _CONFLICT_MARKER_RE.match(line):
                        offenders.append((rel_path, line_no, line.rstrip()))
        except (OSError, UnicodeDecodeError):
            # Skip files that can't be read (e.g. very large binaries or
            # permission issues).  ``errors="ignore"`` handles most decode
            # problems; this is a safety net.
            continue

    return offenders


def test_no_git_conflict_markers_in_repo():
    """There must be zero unresolved conflict markers anywhere in the repo."""
    root = _repo_root()
    offending = _find_conflict_markers(root)

    if offending:
        details = "\n".join(
            f"  {path}:{line_no}: {content}"
            for path, line_no, content in offending
        )
        pytest.fail(
            f"Unresolved git conflict markers found in {len(offending)} location(s):\n"
            f"{details}\n"
            f"Resolve these before committing — use `git status` to identify "
            f"un-merged branches."
        )

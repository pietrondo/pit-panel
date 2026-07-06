"""Software bug and error analysis tool."""

import asyncio
import re
from collections import defaultdict
from typing import Any

SEVERITY_RANK = {"critical": 0, "error": 1, "warning": 2}

NOISE_PATTERNS = [
    re.compile(r"(?i)\bWARN\b.*GlobalExceptionHandler.*No resource at"),
    re.compile(r"(?i)No static resource .* for request"),
    re.compile(r"(?i)\b(?:GET|POST|HEAD)\s+/(?:favicon\.ico|robots\.txt)\b.*\b404\b"),
]

TRIAGE_RULES = [
    (
        "critical",
        re.compile(
            r"(?i)\b(CRITICAL|ExceptionGroup|Traceback \(most recent call last\)|"
            r"panic:|segmentation fault|fatal error)\b"
        ),
        "Crash o eccezione non gestita: controlla stack trace e ultimo deploy.",
    ),
    (
        "error",
        re.compile(
            r"(?i)\b(ERROR|TypeError|ReferenceError|SyntaxError|Unhandled Promise|"
            r"NullPointerException|OperationalError|IntegrityError|RuntimeError)\b"
        ),
        "Errore applicativo: controlla i log del servizio nello stesso timestamp.",
    ),
    (
        "warning",
        re.compile(r"(?i)\b(WARN|WARNING)\b"),
        "Warning: indaga solo se ricorrente o visibile agli utenti.",
    ),
]


def _is_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def _clean_log_line(line: str) -> str:
    line = re.sub(r"^.*?pit-panel\[\d+\]:\s*", "", line.strip())
    line = re.sub(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+", "", line)
    line = re.sub(r"^\w{3}\s+\d{2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+", "", line)
    return line[:300]


def _fingerprint(message: str) -> str:
    fp = message.lower()
    fp = re.sub(r"\b\d{4}-\d{2}-\d{2}[t\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b", "<timestamp>", fp)
    fp = re.sub(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b", "<time>", fp)
    fp = re.sub(r"\b\d+\b", "<n>", fp)
    fp = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", fp)
    fp = re.sub(r"\s+", " ", fp).strip()
    return fp[:160]


def classify_log_line(line: str) -> dict[str, str] | None:
    """Classify a raw log line into a triage issue, or ignore it as noise."""
    if not line.strip() or _is_noise(line):
        return None

    cleaned = _clean_log_line(line)
    for severity, pattern, hint in TRIAGE_RULES:
        if pattern.search(cleaned):
            return {
                "severity": severity,
                "message": cleaned,
                "raw": line.strip()[:500],
                "fingerprint": _fingerprint(cleaned),
                "hint": hint,
            }
    return None


def group_log_issues(lines: list[str], limit: int = 15) -> list[dict[str, Any]]:
    """Group classified log lines by severity and normalized fingerprint."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for line in lines:
        issue = classify_log_line(line)
        if not issue:
            continue

        key = (issue["severity"], issue["fingerprint"])
        if key not in grouped:
            grouped[key] = {
                "severity": issue["severity"],
                "message": issue["message"],
                "raw": issue["raw"],
                "fingerprint": issue["fingerprint"],
                "hint": issue["hint"],
                "count": 0,
            }
        grouped[key]["count"] += 1
        grouped[key]["raw"] = issue["raw"]

    return sorted(
        grouped.values(),
        key=lambda item: (SEVERITY_RANK[item["severity"]], -item["count"], item["message"]),
    )[:limit]


def _summarize_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        counts[issue["severity"]] += int(issue["count"])
    return dict(counts)


def _format_issue(issue: dict[str, Any]) -> str:
    severity = str(issue["severity"]).upper()
    count = int(issue.get("count", 1))
    message = str(issue.get("message", ""))
    hint = str(issue.get("hint", ""))
    fingerprint = str(issue.get("fingerprint", ""))
    return f"[{severity} x{count}] {message} — {hint} — fp:{fingerprint}"


async def analyze_container_logs() -> list[dict[str, Any]]:
    """Scan running Docker containers and return grouped, severity-aware issues."""
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
        for line in stdout.decode().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 1)
            if len(parts) != 2:
                continue
            cid, name = parts

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
            issues = group_log_issues(logs.splitlines(), limit=10)
            if issues:
                counts = _summarize_counts(issues)
                bugs.append(
                    {
                        "container": name,
                        "issues": issues,
                        "errors": [_format_issue(issue) for issue in issues],
                        "count": sum(int(issue["count"]) for issue in issues),
                        "critical": counts.get("critical", 0),
                        "error": counts.get("error", 0),
                        "warning": counts.get("warning", 0),
                    }
                )

        return bugs
    except Exception:
        return []


async def analyze_system_logs() -> list[str]:
    """Scan system logs for grouped Pit Panel issues."""
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

        issues = group_log_issues(stdout.decode(errors="replace").splitlines(), limit=15)
        return [_format_issue(issue) for issue in issues]
    except Exception:
        return []

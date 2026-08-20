from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from pit_panel.security.bug_analyzer import (
    _summarize_counts,
    analyze_container_logs,
    analyze_system_logs,
    classify_log_line,
    group_log_issues,
)


def test_classify_log_line_ignores_static_resource_noise() -> None:
    line = (
        "13:33:20.961 [jetty-971] WARN s.s.S.e.GlobalExceptionHandler - "
        "No resource at /api/v1/policies: No static resource api/v1/policies "
        "for request '/api/v1/policies'."
    )

    assert classify_log_line(line) is None


def test_classify_log_line_detects_real_exception_group() -> None:
    issue = classify_log_line(
        "Jul 02 05:51:12 racknerd python[342996]: | ExceptionGroup: "
        "unhandled errors in a TaskGroup (1 sub-exception)"
    )

    assert issue is not None
    assert issue["severity"] == "critical"
    assert "TaskGroup" in issue["message"]
    assert issue["hint"]


def test_group_log_issues_deduplicates_by_fingerprint() -> None:
    lines = [
        "2026-07-02 10:00:00 ERROR Database timeout for app 123",
        "2026-07-02 10:01:00 ERROR Database timeout for app 456",
        "2026-07-02 10:02:00 WARNING Cache miss for key abc",
    ]

    issues = group_log_issues(lines)

    assert len(issues) == 2
    assert issues[0]["severity"] == "error"
    assert issues[0]["count"] == 2
    assert issues[1]["severity"] == "warning"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("asyncio.create_subprocess_exec")
async def test_analyze_system_logs_success(mock_exec: Any) -> None:
    mock_proc = mock_exec.return_value
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (
        b"2026-07-02 10:00:00 ERROR Database timeout\n2026-07-02 10:01:00 WARNING Cache miss\n",
        b"",
    )

    result = await analyze_system_logs()

    assert len(result) == 2
    assert "ERROR" in result[0]
    assert "Database timeout" in result[0]
    assert "WARNING" in result[1]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("asyncio.create_subprocess_exec")
async def test_analyze_system_logs_journalctl_failure(mock_exec: Any) -> None:
    mock_proc = mock_exec.return_value
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = (b"", b"")

    result = await analyze_system_logs()

    assert result == []


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("asyncio.create_subprocess_exec")
async def test_analyze_system_logs_exception(mock_exec: Any) -> None:
    mock_exec.side_effect = Exception("Failed")

    result = await analyze_system_logs()

    assert result == []




@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("asyncio.create_subprocess_exec")
async def test_analyze_container_logs_success(mock_exec: Any) -> None:
    mock_ps_proc = AsyncMock()
    mock_ps_proc.returncode = 0
    mock_ps_proc.communicate.return_value = (b"cid1|test-app1\ncid2|clamav-server\n", b"")

    mock_logs_proc = AsyncMock()
    mock_logs_proc.returncode = 0
    mock_logs_proc.communicate.return_value = (b"2026-07-02 10:00:00 ERROR Database timeout\n", b"")

    async def side_effect(*args: Any, **kwargs: Any) -> AsyncMock:
        if "ps" in args:
            return mock_ps_proc
        elif "logs" in args:
            return mock_logs_proc
        return AsyncMock()

    mock_exec.side_effect = side_effect

    result = await analyze_container_logs()

    assert len(result) == 1
    assert result[0]["container"] == "test-app1"
    assert result[0]["error"] == 1
    assert result[0]["warning"] == 0

@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("asyncio.create_subprocess_exec")
async def test_analyze_container_logs_failure(mock_exec: Any) -> None:
    mock_ps_proc = AsyncMock()
    mock_ps_proc.returncode = 1
    mock_ps_proc.communicate.return_value = (b"", b"Error")

    mock_exec.return_value = mock_ps_proc

    result = await analyze_container_logs()

    assert result == []

@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("asyncio.create_subprocess_exec")
async def test_analyze_container_logs_timeout(mock_exec: Any) -> None:
    mock_ps_proc = AsyncMock()
    mock_ps_proc.returncode = 0
    mock_ps_proc.communicate.return_value = (b"cid1|test-app1\n", b"")

    mock_logs_proc = AsyncMock()
    mock_logs_proc.communicate.side_effect = TimeoutError()

    async def side_effect(*args: Any, **kwargs: Any) -> AsyncMock:
        if "ps" in args:
            return mock_ps_proc
        elif "logs" in args:
            return mock_logs_proc
        return AsyncMock()

    mock_exec.side_effect = side_effect

    with patch("asyncio.wait_for", side_effect=TimeoutError):
        result = await analyze_container_logs()
        assert result == []

@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@patch("asyncio.create_subprocess_exec")
async def test_analyze_container_logs_exception(mock_exec: Any) -> None:
    mock_exec.side_effect = Exception("General error")

    result = await analyze_container_logs()

    assert result == []

def test_summarize_counts() -> None:
    issues: list[dict[str, Any]] = [
        {"severity": "error", "count": 2},
        {"severity": "error", "count": 1},
        {"severity": "warning", "count": 3}
    ]
    counts = _summarize_counts(issues)

    assert counts["error"] == 3
    assert counts["warning"] == 3

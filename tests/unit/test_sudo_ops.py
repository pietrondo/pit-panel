import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pit_panel.core.sudo_ops import run_cmd, run_sudo


@pytest.fixture
def mock_subprocess():
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"mock stdout", b"mock stderr"))
        mock_proc.kill = MagicMock()  # kill is sync
        mock_exec.return_value = mock_proc
        yield mock_exec, mock_proc


@pytest.mark.asyncio
async def test_run_cmd_success(mock_subprocess):
    mock_exec, mock_proc = mock_subprocess

    result = await run_cmd(["echo", "hello"])

    assert result.stdout == "mock stdout"
    assert result.stderr == "mock stderr"
    assert result.returncode == 0
    mock_exec.assert_called_once_with(
        "echo",
        "hello",
        stdin=None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=None,
    )
    mock_proc.communicate.assert_called_once_with(input=None)


@pytest.mark.asyncio
async def test_run_cmd_timeout(mock_subprocess):
    mock_exec, mock_proc = mock_subprocess
    mock_proc.communicate.side_effect = TimeoutError

    result = await run_cmd(["sleep", "10"], timeout=1)

    assert result.stdout == ""
    assert result.stderr == "Timeout"
    assert result.returncode == -1
    mock_proc.kill.assert_called_once()
    assert (
        mock_proc.communicate.call_count == 2
    )  # 1 for the first call that timeouts, 1 inside the except block


@pytest.mark.asyncio
async def test_run_cmd_exception():
    with patch("asyncio.create_subprocess_exec", side_effect=Exception("mocked error")):
        result = await run_cmd(["ls"])

        assert result.stdout == ""
        assert result.stderr == "mocked error"
        assert result.returncode == -1


@pytest.mark.asyncio
async def test_run_cmd_sudo_injection(mock_subprocess):
    mock_exec, mock_proc = mock_subprocess

    with patch("pit_panel.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.sudo_password = "testpassword"
        mock_get_settings.return_value = mock_settings

        _ = await run_cmd(["sudo", "-n", "whoami"])

        mock_exec.assert_called_once_with(
            "sudo",
            "-S",
            "whoami",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=None,
        )
        mock_proc.communicate.assert_called_once_with(input=b"testpassword\n")


@pytest.mark.asyncio
async def test_run_sudo_success(mock_subprocess):
    mock_exec, mock_proc = mock_subprocess

    result = await run_sudo(["systemctl", "status", "docker"], "mypass")

    assert result == "mock stdoutmock stderr"
    mock_exec.assert_called_once_with(
        "sudo",
        "-S",
        "-p",
        "",
        "systemctl",
        "status",
        "docker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_proc.communicate.assert_called_once_with(input=b"mypass\n")


@pytest.mark.asyncio
async def test_run_sudo_invalid_command():
    with pytest.raises(ValueError, match="Command 'rm' is not allowed"):
        await run_sudo(["rm", "-rf", "/"], "mypass")


@pytest.mark.asyncio
async def test_run_sudo_empty_command():
    with pytest.raises(ValueError, match="Command cannot be empty"):
        await run_sudo([], "mypass")

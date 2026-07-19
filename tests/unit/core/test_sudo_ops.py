import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from pit_panel.core.sudo_ops import run_sudo


@pytest.mark.asyncio
async def test_run_sudo_empty_command():
    with pytest.raises(ValueError, match="Command cannot be empty"):
        await run_sudo([], "password")


@pytest.mark.asyncio
async def test_run_sudo_not_allowed_command():
    with pytest.raises(ValueError, match="Command 'not_allowed' is not allowed"):
        await run_sudo(["not_allowed"], "password")


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_sudo_success(mock_create_subprocess_exec):
    auth_proc = AsyncMock()
    auth_proc.returncode = 0
    auth_proc.communicate.return_value = (b"", b"")

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"output_stdout", b"")
    reset_proc = AsyncMock()
    reset_proc.returncode = 0
    reset_proc.communicate.return_value = (b"", b"")
    mock_create_subprocess_exec.side_effect = [auth_proc, mock_proc, reset_proc]

    result = await run_sudo(["systemctl", "status"], "password")

    assert result == "output_stdout"
    mock_create_subprocess_exec.assert_any_call(
        "sudo",
        "-n",
        "systemctl",
        "status",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )



@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_sudo_with_stderr(mock_create_subprocess_exec):
    auth_proc = AsyncMock()
    auth_proc.returncode = 0
    auth_proc.communicate.return_value = (b"", b"")

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"output_stdout", b"output_stderr")
    reset_proc = AsyncMock()
    reset_proc.returncode = 0
    reset_proc.communicate.return_value = (b"", b"")
    mock_create_subprocess_exec.side_effect = [auth_proc, mock_proc, reset_proc]

    result = await run_sudo(["systemctl", "status"], "password")

    assert result == "output_stdoutoutput_stderr"
    mock_create_subprocess_exec.assert_any_call(
        "sudo",
        "-n",
        "systemctl",
        "status",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )



@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_sudo_empty_output(mock_create_subprocess_exec):
    auth_proc = AsyncMock()
    auth_proc.returncode = 0
    auth_proc.communicate.return_value = (b"", b"")

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"", b"")
    reset_proc = AsyncMock()
    reset_proc.returncode = 0
    reset_proc.communicate.return_value = (b"", b"")
    mock_create_subprocess_exec.side_effect = [auth_proc, mock_proc, reset_proc]

    result = await run_sudo(["systemctl", "status"], "password")

    assert result == ""
    mock_create_subprocess_exec.assert_any_call(
        "sudo",
        "-n",
        "systemctl",
        "status",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

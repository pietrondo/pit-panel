import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from pit_panel.core.sudo_ops import run_sudo, ALLOWED_COMMANDS

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
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"output_stdout", b"")
    mock_create_subprocess_exec.return_value = mock_proc

    result = await run_sudo(["systemctl", "status"], "password")

    assert result == "output_stdout"
    mock_create_subprocess_exec.assert_called_once_with(
        "sudo", "-S", "-p", "", "systemctl", "status",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_proc.communicate.assert_called_once_with(input=b"password\n")

@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_sudo_with_stderr(mock_create_subprocess_exec):
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"output_stdout", b"output_stderr")
    mock_create_subprocess_exec.return_value = mock_proc

    result = await run_sudo(["systemctl", "status"], "password")

    assert result == "output_stdoutoutput_stderr"
    mock_create_subprocess_exec.assert_called_once_with(
        "sudo", "-S", "-p", "", "systemctl", "status",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_proc.communicate.assert_called_once_with(input=b"password\n")

@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_sudo_empty_output(mock_create_subprocess_exec):
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_create_subprocess_exec.return_value = mock_proc

    result = await run_sudo(["systemctl", "status"], "password")

    assert result == ""
    mock_create_subprocess_exec.assert_called_once_with(
        "sudo", "-S", "-p", "", "systemctl", "status",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_proc.communicate.assert_called_once_with(input=b"password\n")

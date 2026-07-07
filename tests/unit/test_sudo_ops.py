import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pit_panel.core.sudo_ops import CmdResult, run_cmd


@pytest.fixture
def mock_settings():
    with patch("pit_panel.config.get_settings") as mock:
        settings = MagicMock()
        settings.sudo_password = None
        mock.return_value = settings
        yield settings

@pytest.fixture
def mock_subprocess():
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock:
        process = MagicMock()
        process.communicate = AsyncMock(return_value=(b"test stdout", b"test stderr"))
        process.returncode = 0
        mock.return_value = process
        yield mock

@pytest.mark.asyncio
async def test_run_cmd_success(mock_subprocess, mock_settings):
    result = await run_cmd(["echo", "hello"])

    assert isinstance(result, CmdResult)
    assert result.stdout == "test stdout"
    assert result.stderr == "test stderr"
    assert result.returncode == 0

    mock_subprocess.assert_called_once_with(
        "echo", "hello",
        stdin=None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=None
    )

@pytest.mark.asyncio
async def test_run_cmd_sudo_injection(mock_subprocess, mock_settings):
    mock_settings.sudo_password = "mypassword"

    result = await run_cmd(["sudo", "ls"])

    assert isinstance(result, CmdResult)

    mock_subprocess.assert_called_once_with(
        "sudo", "-S", "ls",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=None
    )

    # communicate should have been called with input
    process = mock_subprocess.return_value
    process.communicate.assert_called_once_with(input=b"mypassword\n")

@pytest.mark.asyncio
async def test_run_cmd_sudo_injection_with_n(mock_subprocess, mock_settings):
    mock_settings.sudo_password = "mypassword"

    result = await run_cmd(["sudo", "-n", "ls"])

    assert isinstance(result, CmdResult)

    mock_subprocess.assert_called_once_with(
        "sudo", "-S", "ls",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=None
    )

@pytest.mark.asyncio
async def test_run_cmd_timeout(mock_subprocess, mock_settings):
    process = mock_subprocess.return_value
    process.communicate.side_effect = TimeoutError()

    result = await run_cmd(["sleep", "10"])

    assert isinstance(result, CmdResult)
    assert result.stdout == ""
    assert result.stderr == "Timeout"
    assert result.returncode == -1
    process.kill.assert_called_once()

@pytest.mark.asyncio
async def test_run_cmd_exception(mock_subprocess, mock_settings):
    mock_subprocess.side_effect = Exception("Test Error")

    result = await run_cmd(["badcmd"])

    assert isinstance(result, CmdResult)
    assert result.stdout == ""
    assert result.stderr == "Test Error"
    assert result.returncode == -1

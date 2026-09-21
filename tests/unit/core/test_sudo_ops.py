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


@pytest.mark.asyncio
async def test_run_cmd_basic():
    from pit_panel.core.sudo_ops import run_cmd

    result = await run_cmd(["echo", "hello"])
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""
    assert result.returncode == 0


@pytest.mark.asyncio
async def test_run_cmd_input():
    from pit_panel.core.sudo_ops import run_cmd

    result = await run_cmd(["cat"], input="test input")
    assert result.stdout == "test input"
    assert result.returncode == 0


@pytest.mark.asyncio
@patch("pit_panel.config.get_settings")
@patch("asyncio.create_subprocess_exec")
async def test_run_cmd_sudo_success(mock_create_subprocess_exec, mock_get_settings):
    mock_settings = mock_get_settings.return_value
    mock_settings.sudo_password = "password"

    auth_proc = AsyncMock()
    auth_proc.returncode = 0
    auth_proc.communicate.return_value = (b"", b"")

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"sudo output", b"")

    reset_proc = AsyncMock()
    reset_proc.returncode = 0
    reset_proc.communicate.return_value = (b"", b"")

    mock_create_subprocess_exec.side_effect = [auth_proc, mock_proc, reset_proc]

    from pit_panel.core.sudo_ops import run_cmd

    result = await run_cmd(["sudo", "-n", "systemctl", "status"])

    assert result.stdout == "sudo output"
    assert result.returncode == 0


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_cmd_timeout(mock_create_subprocess_exec):
    mock_proc = AsyncMock()

    async def slow_communicate(*args, **kwargs):
        await asyncio.sleep(2)
        return (b"", b"")

    mock_proc.communicate.side_effect = slow_communicate

    mock_create_subprocess_exec.return_value = mock_proc

    from pit_panel.core.sudo_ops import run_cmd

    result = await run_cmd(["sleep", "10"], timeout=1)

    assert result.stderr == "Timeout"
    assert result.returncode == -1


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_cmd_exception(mock_create_subprocess_exec):
    mock_create_subprocess_exec.side_effect = Exception("General error")

    from pit_panel.core.sudo_ops import run_cmd

    result = await run_cmd(["invalid_command"])

    assert result.stderr == "General error"
    assert result.returncode == -1


@pytest.mark.asyncio
@patch("pit_panel.config.get_settings")
@patch("asyncio.create_subprocess_exec")
async def test_run_cmd_sudo_auth_timeout(mock_create_subprocess_exec, mock_get_settings):
    mock_settings = mock_get_settings.return_value
    mock_settings.sudo_password = "password"

    auth_proc = AsyncMock()

    async def slow_communicate(*args, **kwargs):
        await asyncio.sleep(2)
        return (b"", b"")

    auth_proc.communicate.side_effect = slow_communicate

    mock_create_subprocess_exec.side_effect = [auth_proc]

    from pit_panel.core.sudo_ops import run_cmd

    result = await run_cmd(["sudo", "-n", "systemctl", "status"], timeout=1)

    assert result.stderr == "sudo authentication timeout"
    assert result.returncode == -1


@pytest.mark.asyncio
@patch("pit_panel.config.get_settings")
@patch("asyncio.create_subprocess_exec")
async def test_run_cmd_sudo_auth_failed(mock_create_subprocess_exec, mock_get_settings):
    mock_settings = mock_get_settings.return_value
    mock_settings.sudo_password = "password"

    auth_proc = AsyncMock()
    auth_proc.returncode = 1
    auth_proc.communicate.return_value = (b"", b"")

    mock_create_subprocess_exec.side_effect = [auth_proc]

    from pit_panel.core.sudo_ops import run_cmd

    result = await run_cmd(["sudo", "-n", "systemctl", "status"])

    assert result.stderr == "sudo authentication failed"
    assert result.returncode == -1


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_sudo_auth_timeout(mock_create_subprocess_exec):
    auth_proc = AsyncMock()

    async def slow_communicate(*args, **kwargs):
        await asyncio.sleep(2)
        return (b"", b"")

    auth_proc.communicate.side_effect = slow_communicate

    mock_create_subprocess_exec.side_effect = [auth_proc]

    from pit_panel.core.sudo_ops import run_sudo

    # We patch wait_for timeout inside run_sudo which is hardcoded to 10s
    # but we will patch asyncio.wait_for to raise TimeoutError
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await run_sudo(["systemctl", "status"], "password")

    assert result == "incorrect password attempt (timeout)"


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_run_sudo_auth_failed(mock_create_subprocess_exec):
    auth_proc = AsyncMock()
    auth_proc.returncode = 1
    auth_proc.communicate.return_value = (b"", b"")

    mock_create_subprocess_exec.side_effect = [auth_proc]

    from pit_panel.core.sudo_ops import run_sudo

    result = await run_sudo(["systemctl", "status"], "password")

    assert result == "incorrect password attempt"

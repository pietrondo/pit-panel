from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.security import (
    _ensure_fail2ban_jails,
    _fail2ban_status,
    _firewall_status,
    _run_cmd,
    ban_ip_address,
    unban_ip_address,
)


@pytest.mark.asyncio
async def test_run_cmd_success():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"output\n", b"")
        mock_exec.return_value = mock_process

        result = await _run_cmd(["echo", "output"])

        assert result == "output"
        import asyncio

        mock_exec.assert_called_once_with(
            "echo",
            "output",
            stdin=None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_run_cmd_stderr_fallback():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error\n")
        mock_exec.return_value = mock_process

        result = await _run_cmd(["echo", "error"])

        assert result == "error"


@pytest.mark.asyncio
async def test_run_cmd_exception():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = Exception("error")

        result = await _run_cmd(["invalid"])

        assert result == "unavailable"


@pytest.mark.asyncio
async def test_firewall_status_active():
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.return_value = "Status: active\n\nTo\n--\n80/tcp\n"

        result = await _firewall_status()

        assert result["active"] is True
        assert "80/tcp" in result["rules"]


@pytest.mark.asyncio
async def test_firewall_status_inactive():
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        # First call returns inactive, second returns enable, then allows, then active
        mock_run_cmd.side_effect = [
            "Status: inactive\n",
            "Firewall is active and enabled on system startup\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            "Status: active\n\nTo\n--\n80/tcp\n",
        ]

        result = await _firewall_status()

        assert result["active"] is True
        assert "80/tcp" in result["rules"]


@pytest.mark.asyncio
async def test_firewall_status_not_found():
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.side_effect = [
            "ufw: command not found\n",
            "Setting up ufw\n",
            "Firewall is active and enabled on system startup\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            "Status: active\n\nTo\n--\n80/tcp\n",
        ]

        result = await _firewall_status()

        assert result["active"] is True
        assert "80/tcp" in result["rules"]


@pytest.mark.asyncio
async def test_fail2ban_status_active():
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.return_value = "Status\n|- Number of jail:\t1\n`- sshd\n"

        result = await _fail2ban_status()

        assert result["active"] is True
        assert "sshd" in result["jails"]


@pytest.mark.asyncio
async def test_fail2ban_status_not_found():
    with (
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd,
        patch("pit_panel.core.security._ensure_fail2ban_jails") as mock_ensure,
    ):
        mock_run_cmd.side_effect = [
            "fail2ban-client: command not found\n",
            "Setting up fail2ban\n",
            "Status\n|- Number of jail:\t1\n`- sshd\n",
        ]

        result = await _fail2ban_status()

        assert result["active"] is True
        assert "sshd" in result["jails"]
        mock_ensure.assert_called_once()


@pytest.mark.asyncio
async def test_fail2ban_status_no_jails():
    with (
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd,
        patch("pit_panel.core.security._ensure_fail2ban_jails") as mock_ensure,
    ):
        mock_run_cmd.side_effect = [
            "Status\n|- Number of jail:\t0\n`- Jail list:\t\n",
            "Status\n|- Number of jail:\t1\n`- sshd\n",
        ]

        result = await _fail2ban_status()

        assert result["active"] is True
        assert "sshd" in result["jails"]
        mock_ensure.assert_called_once()


@pytest.mark.asyncio
async def test_fail2ban_status_sudo_required():
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.return_value = "sudo: a password is required"

        result = await _fail2ban_status()

        assert result["active"] is False
        assert result["jails"] == []


@pytest.mark.asyncio
async def test_ensure_fail2ban_jails():
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        await _ensure_fail2ban_jails()

        assert mock_run_cmd.call_count == 2

        # Check the first call was tee
        call_args = mock_run_cmd.call_args_list[0][0][0]
        assert "tee" in call_args

        # Check the second call was restart
        call_args = mock_run_cmd.call_args_list[1][0][0]
        assert "restart" in call_args


@pytest.mark.asyncio
async def test_ban_ip_address():
    mock_db = AsyncMock(spec=AsyncSession)

    with (
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd,
        patch("pit_panel.core.security.ban_ip", new_callable=AsyncMock) as mock_ban_ip,
    ):
        mock_ban_ip.return_value = True

        result = await ban_ip_address(mock_db, "1.2.3.4", "Test reason", 60)

        assert result is True
        mock_run_cmd.assert_called_once_with(["sudo", "-n", "ufw", "deny", "from", "1.2.3.4"])
        mock_ban_ip.assert_called_once_with(mock_db, "1.2.3.4", "Test reason", 60)


@pytest.mark.asyncio
async def test_ban_ip_address_ufw_fails():
    mock_db = AsyncMock(spec=AsyncSession)

    with (
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd,
        patch("pit_panel.core.security.ban_ip", new_callable=AsyncMock) as mock_ban_ip,
    ):
        mock_run_cmd.side_effect = Exception("UFW failed")
        mock_ban_ip.return_value = True

        result = await ban_ip_address(mock_db, "1.2.3.4", "Test reason", 60)

        assert result is True
        mock_ban_ip.assert_called_once_with(mock_db, "1.2.3.4", "Test reason", 60)


@pytest.mark.asyncio
async def test_unban_ip_address():
    mock_db = AsyncMock(spec=AsyncSession)

    with (
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd,
        patch("pit_panel.security.ipban.unban_ip", new_callable=AsyncMock) as mock_unban_ip,
    ):
        mock_unban_ip.return_value = True

        sys_dict = {"pit_panel.security.ipban": MagicMock(unban_ip=mock_unban_ip)}
        with patch.dict("sys.modules", sys_dict):
            result = await unban_ip_address(mock_db, "1.2.3.4", 1)

        assert result is True
        mock_run_cmd.assert_called_once_with(
            ["sudo", "-n", "ufw", "delete", "deny", "from", "1.2.3.4"]
        )
        mock_unban_ip.assert_called_once_with(mock_db, "1.2.3.4", 1)


@pytest.mark.asyncio
async def test_run_cmd_sudo_with_password():
    from pit_panel.config import Settings

    test_settings = Settings(sudo_password="supersecurepassword")

    with (
        patch("pit_panel.config.get_settings", return_value=test_settings),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"success\n", b"")
        mock_exec.return_value = mock_process

        result = await _run_cmd(["sudo", "-n", "ufw", "status"])

        assert result == "success"

        import asyncio

        mock_exec.assert_called_once_with(
            "sudo",
            "-S",
            "ufw",
            "status",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        mock_process.communicate.assert_called_once_with(input=b"supersecurepassword\n")


@pytest.mark.asyncio
async def test_run_cmd_sudo_with_password_and_existing_input():
    from pit_panel.config import Settings

    test_settings = Settings(sudo_password="supersecurepassword")

    with (
        patch("pit_panel.config.get_settings", return_value=test_settings),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"success\n", b"")
        mock_exec.return_value = mock_process

        result = await _run_cmd(["sudo", "-n", "ufw", "status"], input="custom_input")

        assert result == "success"

        import asyncio

        mock_exec.assert_called_once_with(
            "sudo",
            "-S",
            "ufw",
            "status",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        mock_process.communicate.assert_called_once_with(input=b"supersecurepassword\ncustom_input")

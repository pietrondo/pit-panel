from unittest.mock import AsyncMock, MagicMock, mock_open, patch

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


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_run_cmd_success() -> None:
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
            cwd=None,
        )


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_run_cmd_stderr_fallback() -> None:
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error\n")
        mock_exec.return_value = mock_process

        result = await _run_cmd(["echo", "error"])

        assert result == "error"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_run_cmd_exception() -> None:
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = Exception("error")

        result = await _run_cmd(["invalid"])

        assert result == "unavailable"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_firewall_status_active() -> None:
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.return_value = (
            "Status: active\n\n"
            "     To                         Action      From\n"
            "     --                         ------      ----\n"
            "[ 1] 80/tcp                     ALLOW IN    Anywhere\n"
        )

        result = await _firewall_status()

        assert result["active"] is True
        assert len(result["rules"]) == 1
        assert result["rules"][0]["port"] == "80"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_firewall_status_inactive() -> None:
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        # First call returns inactive, second returns enable, then allows, then active
        mock_run_cmd.side_effect = [
            "Status: inactive\n",
            "Firewall is active and enabled on system startup\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            (
                "Status: active\n\n"
                "     To                         Action      From\n"
                "     --                         ------      ----\n"
                "[ 1] 80/tcp                     ALLOW IN    Anywhere\n"
            ),
        ]

        result = await _firewall_status()

        assert result["active"] is True
        assert len(result["rules"]) == 1
        assert result["rules"][0]["port"] == "80"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_firewall_status_not_found() -> None:
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.side_effect = [
            "ufw: command not found\n",
            "Setting up ufw\n",
            "Firewall is active and enabled on system startup\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            "Rule added\n",
            (
                "Status: active\n\n"
                "     To                         Action      From\n"
                "     --                         ------      ----\n"
                "[ 1] 80/tcp                     ALLOW IN    Anywhere\n"
            ),
        ]

        result = await _firewall_status()

        assert result["active"] is True
        assert len(result["rules"]) == 1
        assert result["rules"][0]["port"] == "80"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_fail2ban_status_active() -> None:
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.return_value = "Status\n|- Number of jail:\t1\n`- sshd\n"

        result = await _fail2ban_status()

        assert result["active"] is True
        assert "sshd" in result["jails"]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_fail2ban_status_not_found() -> None:
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


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_fail2ban_status_no_jails() -> None:
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


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_fail2ban_status_sudo_required() -> None:
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        mock_run_cmd.return_value = "sudo: a password is required"

        result = await _fail2ban_status()

        assert result["active"] is False
        assert result["jails"] == []


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ensure_fail2ban_jails() -> None:
    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run_cmd:
        await _ensure_fail2ban_jails()

        assert mock_run_cmd.call_count == 2

        # Check the first call was tee
        call_args = mock_run_cmd.call_args_list[0][0][0]
        assert "tee" in call_args

        # Check the second call was restart
        call_args = mock_run_cmd.call_args_list[1][0][0]
        assert "restart" in call_args


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ban_ip_address() -> None:
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


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ban_ip_address_ufw_fails() -> None:
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


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_unban_ip_address() -> None:
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


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_run_cmd_sudo_with_password() -> None:
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
            cwd=None,
        )
        mock_process.communicate.assert_called_once_with(input=b"supersecurepassword\n")


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_run_cmd_sudo_with_password_and_existing_input() -> None:
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
            cwd=None,
        )
        mock_process.communicate.assert_called_once_with(input=b"supersecurepassword\ncustom_input")


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_get_client_ip() -> None:
    from fastapi import Request
    from starlette.datastructures import Headers

    from pit_panel.core.security import _get_client_ip

    # 1. Test X-Forwarded-For
    req = MagicMock(spec=Request)
    req.headers = Headers({"x-forwarded-for": "203.0.113.195, 70.41.3.18"})
    assert _get_client_ip(req) == "203.0.113.195"

    # 2. Test X-Real-IP
    req = MagicMock(spec=Request)
    req.headers = Headers({"x-real-ip": "203.0.113.196"})
    assert _get_client_ip(req) == "203.0.113.196"

    # 3. Test fallback
    req = MagicMock(spec=Request)
    req.headers = Headers({})
    req.client = MagicMock()
    req.client.host = "203.0.113.197"
    assert _get_client_ip(req) == "203.0.113.197"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_detect_ssh_port_success() -> None:
    from unittest.mock import mock_open

    from pit_panel.core.security import _detect_ssh_port

    with patch("builtins.open", mock_open(read_data="Port 2222\n")):
        port = await _detect_ssh_port()
        assert port == 2222


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_detect_ssh_port_permission_fallback() -> None:
    from pit_panel.core.security import _detect_ssh_port

    with (
        patch("builtins.open", side_effect=PermissionError("Permission denied")),
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run,
    ):
        mock_run.return_value = "Port 4422\n"
        port = await _detect_ssh_port()
        assert port == 4422
        mock_run.assert_called_with(["sudo", "-n", "cat", "/etc/ssh/sshd_config"])


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_detect_ssh_port_fallback_default() -> None:
    from pit_panel.core.security import _detect_ssh_port

    with patch("builtins.open", side_effect=FileNotFoundError()):
        port = await _detect_ssh_port()
        assert port == 22


def test_parse_ufw_rules() -> None:
    from pit_panel.core.security import _parse_ufw_rules

    output = """
Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    Anywhere
[ 2] 80/udp                     DENY IN     1.2.3.4
[ 3] 443                        LIMIT IN    Anywhere (v6)
"""
    rules = _parse_ufw_rules(output)
    assert len(rules) == 3
    assert rules[0] == {
        "index": 1,
        "port": "22",
        "protocol": "tcp",
        "action": "ALLOW IN",
        "source": "Anywhere",
        "raw": "[ 1] 22/tcp                     ALLOW IN    Anywhere",
    }
    assert rules[1] == {
        "index": 2,
        "port": "80",
        "protocol": "udp",
        "action": "DENY IN",
        "source": "1.2.3.4",
        "raw": "[ 2] 80/udp                     DENY IN     1.2.3.4",
    }
    assert rules[2] == {
        "index": 3,
        "port": "443",
        "protocol": "any",
        "action": "LIMIT IN",
        "source": "Anywhere (v6)",
        "raw": "[ 3] 443                        LIMIT IN    Anywhere (v6)",
    }


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ufw_delete_rule_lockout() -> None:
    from pit_panel.core.security import _delete_ufw_rule

    with patch("pit_panel.core.security._firewall_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = {
            "active": True,
            "rules": [
                {
                    "index": 1,
                    "port": "22",
                    "protocol": "tcp",
                    "action": "ALLOW IN",
                    "source": "Anywhere",
                    "raw": "",
                },
                {
                    "index": 2,
                    "port": "80",
                    "protocol": "tcp",
                    "action": "ALLOW IN",
                    "source": "1.2.3.4",
                    "raw": "",
                },
            ],
        }

        with pytest.raises(ValueError, match="Cannot delete active SSH rule"):
            await _delete_ufw_rule(1, client_ip="1.2.3.4", ssh_port=22)

        with pytest.raises(ValueError, match="Cannot delete active client IP bypass rule"):
            await _delete_ufw_rule(2, client_ip="1.2.3.4", ssh_port=22)


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ufw_lockout_protection_on_enable() -> None:
    from pit_panel.core.security import _enable_ufw

    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "success"

        ok = await _enable_ufw(client_ip="1.2.3.4", ssh_port=22)
        assert ok is True

        assert mock_run.call_count == 5
        mock_run.assert_any_call(["sudo", "-n", "ufw", "allow", "22/tcp"])
        mock_run.assert_any_call(["sudo", "-n", "ufw", "allow", "from", "1.2.3.4"])
        mock_run.assert_any_call(["sudo", "-n", "ufw", "--force", "enable"])


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_get_jail_config() -> None:
    from pit_panel.core.security import _get_jail_config

    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = ["3600", "600", "5"]

        cfg = await _get_jail_config("sshd")
        assert cfg == {"bantime": 3600, "findtime": 600, "maxretry": 5}
        assert mock_run.call_count == 3


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_save_jail_config_success() -> None:
    from pit_panel.core.security import _save_jail_config

    with patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            "Permission denied",
            "success",
            "success",
        ]

        with patch("builtins.open", side_effect=PermissionError()):
            ok = await _save_jail_config("sshd", bantime=3600, findtime=600, maxretry=5)
            assert ok is True

            write_call = mock_run.call_args_list[1][0][0]
            assert "tee" in write_call
            assert "/etc/fail2ban/jail.d/pit-panel-overrides.local" in write_call

            input_content = mock_run.call_args_list[1][1].get("input", "")
            assert "[sshd]" in input_content
            assert "bantime = 3600" in input_content

            reload_call = mock_run.call_args_list[2][0][0]
            assert "fail2ban-client" in reload_call
            assert "reload" in reload_call


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_save_jail_config_validation() -> None:
    from pit_panel.core.security import _save_jail_config

    with pytest.raises(ValueError, match="Parameters must be positive integers"):
        await _save_jail_config("sshd", bantime=-10, findtime=600, maxretry=5)

    with pytest.raises(ValueError, match="Parameters must be positive integers"):
        await _save_jail_config("sshd", bantime="invalid", findtime=600, maxretry=5)


def test_parse_lynis_report() -> None:
    from pit_panel.core.security import _parse_lynis_report

    dat_content = """
# Comments here
hardening_index=75
warning[]=SSH is open
suggestion[]=Close SSH
suggestion[]=Add firewall rules
"""
    res = _parse_lynis_report(dat_content)
    assert res["hardening_index"] == 75
    assert res["warnings"] == ["SSH is open"]
    assert res["suggestions"] == ["Close SSH", "Add firewall rules"]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_run_lynis_audit_success() -> None:
    from pit_panel.core.security import run_lynis_audit

    with (
        patch("shutil.which", return_value="/usr/bin/lynis"),
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run,
        patch("builtins.open", mock_open(read_data="hardening_index=80\n")),
        patch("os.makedirs"),
    ):
        mock_run.return_value = "success"

        report = await run_lynis_audit()
        assert report["hardening_index"] == 80
        mock_run.assert_called_once_with(
            ["sudo", "-n", "lynis", "audit", "system", "--quick"], timeout=180
        )


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_run_lynis_audit_missing_install_success() -> None:
    from pit_panel.core.security import run_lynis_audit

    # First shutil.which returns None, second returns path
    with (
        patch("shutil.which", side_effect=[None, "/usr/bin/lynis"]),
        patch("pit_panel.core.security._run_cmd", new_callable=AsyncMock) as mock_run,
        patch("builtins.open", mock_open(read_data="hardening_index=80\n")),
        patch("os.makedirs"),
    ):
        mock_run.side_effect = [
            "Setting up lynis",  # apt-get install
            "success",  # run audit
        ]

        report = await run_lynis_audit()
        assert report["hardening_index"] == 80
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["sudo", "-n", "apt-get", "install", "-y", "lynis"], timeout=60)


def test_parse_ufw_rules_edge_cases() -> None:
    from pit_panel.core.security import _parse_ufw_rules

    output = """
Status: active

     To                         Action      From
     --                         ------      ----
[  1] 80/tcp                     ALLOW IN    Anywhere
[ 10] 443/gre                    LIMIT OUT   192.168.1.1
[100] 8080                       DENY        Anywhere (v6)
[ 15] Any                        ALLOW OUT   10.0.0.0/8
This is an invalid line that should be ignored
[ invalid] 22/tcp                ALLOW IN    Anywhere
"""
    rules = _parse_ufw_rules(output)

    assert len(rules) == 4

    # Test whitespace handling in index and standard tcp protocol
    assert rules[0] == {
        "index": 1,
        "port": "80",
        "protocol": "tcp",
        "action": "ALLOW IN",
        "source": "Anywhere",
        "raw": "[  1] 80/tcp                     ALLOW IN    Anywhere",
    }

    # Test unknown protocol fallback to "any" and multi-digit index
    assert rules[1] == {
        "index": 10,
        "port": "443",
        "protocol": "any",
        "action": "LIMIT OUT",
        "source": "192.168.1.1",
        "raw": "[ 10] 443/gre                    LIMIT OUT   192.168.1.1",
    }

    # Test no protocol (fallback "any") and 3-digit index and DENY action
    assert rules[2] == {
        "index": 100,
        "port": "8080",
        "protocol": "any",
        "action": "DENY",
        "source": "Anywhere (v6)",
        "raw": "[100] 8080                       DENY        Anywhere (v6)",
    }

    # Test ALLOW OUT action
    assert rules[3] == {
        "index": 15,
        "port": "Any",
        "protocol": "any",
        "action": "ALLOW OUT",
        "source": "10.0.0.0/8",
        "raw": "[ 15] Any                        ALLOW OUT   10.0.0.0/8",
    }

    # Test empty input
    assert _parse_ufw_rules("") == []

    # Test input with only invalid lines
    assert _parse_ufw_rules("invalid line\nanother one") == []

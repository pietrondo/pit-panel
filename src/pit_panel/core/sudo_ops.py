"""Sudo operations for system management."""

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path

ALLOWED_COMMANDS = {
    "systemctl",
    "apt-get",
    "apt",
    "journalctl",
    "df",
    "free",
    "reboot",
    "uptime",
    "docker",
}


@dataclass
class CmdResult:
    stdout: str
    stderr: str
    returncode: int


async def run_cmd(
    cmd: list[str],
    timeout: int = 10,
    cwd: str | None = None,
    input: str | None = None,
) -> CmdResult:
    """Run a command asynchronously with a timeout, optional working directory, and stdin input."""
    import asyncio

    use_sudo = bool(cmd and cmd[0] == "sudo" and "-n" in cmd)
    sudo_password = None

    if use_sudo:
        from pit_panel.config import get_settings
        settings = get_settings()
        sudo_password = settings.sudo_password.strip() if settings.sudo_password else None

    # Authenticate via sudo -v if a password is provided
    if use_sudo and sudo_password:
        auth_proc = await asyncio.create_subprocess_exec(
            "sudo", "-S", "-p", "", "-v",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(
                auth_proc.communicate((sudo_password + "\n").encode()),
                timeout=timeout
            )
        except TimeoutError:
            with contextlib.suppress(Exception):
                auth_proc.kill()
                await auth_proc.communicate()
            return CmdResult(stdout="", stderr="sudo authentication timeout", returncode=-1)
        if auth_proc.returncode != 0:
            return CmdResult(stdout="", stderr="sudo authentication failed", returncode=-1)

    input_bytes = input.encode() if input is not None else None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=input_bytes), timeout=timeout
        )
        result = CmdResult(
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            returncode=proc.returncode or 0,
        )
    except TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
            await proc.communicate()
        result = CmdResult(stdout="", stderr="Timeout", returncode=-1)
    except Exception as e:
        result = CmdResult(stdout="", stderr=str(e), returncode=-1)

    if use_sudo and sudo_password:
        with contextlib.suppress(Exception):
            reset_proc = await asyncio.create_subprocess_exec("sudo", "-K")
            await reset_proc.communicate()

    return result


async def run_sudo(cmd: list[str], sudo_password: str) -> str:
    """Run a command using sudo securely."""
    if not cmd:
        raise ValueError("Command cannot be empty")

    base_cmd = Path(cmd[0]).name
    if base_cmd not in ALLOWED_COMMANDS:
        raise ValueError(f"Command '{base_cmd}' is not allowed")

    import asyncio

    # Authenticate first
    auth_proc = await asyncio.create_subprocess_exec(
        "sudo", "-S", "-p", "", "-v",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(
            auth_proc.communicate((sudo_password.strip() + "\n").encode()),
            timeout=10
        )
    except TimeoutError:
        with contextlib.suppress(Exception):
            auth_proc.kill()
            await auth_proc.communicate()
        return "incorrect password attempt (timeout)"

    if auth_proc.returncode != 0:
        return "incorrect password attempt"

    # Use sudo -n <cmd>
    full_cmd = ["sudo", "-n"] + cmd

    proc = await asyncio.create_subprocess_exec(
        *full_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    # Clear cached credentials
    with contextlib.suppress(Exception):
        reset_proc = await asyncio.create_subprocess_exec("sudo", "-K")
        await reset_proc.communicate()

    output = ""
    if stdout:
        output += stdout.decode(errors="replace")
    if stderr:
        output += stderr.decode(errors="replace")

    return output

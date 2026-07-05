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
    """Run a command asynchronously with a timeout, optional working directory, and stdin input.
    Automatically injects the sudo password if the command starts with sudo and a password is
    configured.
    """
    from pit_panel.config import get_settings

    # Check for sudo password and replace -n/inject -S
    try:
        settings = get_settings()
        if cmd and cmd[0] == "sudo" and settings.sudo_password:
            new_cmd = list(cmd)
            if len(new_cmd) > 1 and new_cmd[1] == "-n":
                new_cmd[1] = "-S"
            elif "-n" in new_cmd:
                idx = new_cmd.index("-n")
                new_cmd[idx] = "-S"
            else:
                new_cmd.insert(1, "-S")
            cmd = new_cmd

            pw_prefix = f"{settings.sudo_password}\n"
            input = pw_prefix + input if input is not None else pw_prefix
    except Exception:
        pass

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
        return CmdResult(
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            returncode=proc.returncode or 0,
        )
    except TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
            await proc.communicate()
        return CmdResult(stdout="", stderr="Timeout", returncode=-1)
    except Exception as e:
        return CmdResult(stdout="", stderr=str(e), returncode=-1)


async def run_sudo(cmd: list[str], sudo_password: str) -> str:
    """Run a command using sudo, providing the password via stdin."""
    if not cmd:
        raise ValueError("Command cannot be empty")

    base_cmd = Path(cmd[0]).name
    if base_cmd not in ALLOWED_COMMANDS:
        raise ValueError(f"Command '{base_cmd}' is not allowed")

    # Use sudo -S -p '' <cmd>
    full_cmd = ["sudo", "-S", "-p", ""] + cmd

    proc = await asyncio.create_subprocess_exec(
        *full_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    password_input = (sudo_password.strip() + "\n").encode()
    stdout, stderr = await proc.communicate(input=password_input)

    output = ""
    if stdout:
        output += stdout.decode(errors="replace")
    if stderr:
        output += stderr.decode(errors="replace")

    return output

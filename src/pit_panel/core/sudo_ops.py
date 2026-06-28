"""Sudo operations for system management."""

import asyncio

ALLOWED_COMMANDS = {"systemctl", "apt-get", "journalctl", "df", "free", "reboot"}


async def run_sudo(cmd: list[str], sudo_password: str) -> str:
    """Run a command using sudo, providing the password via stdin."""
    if not cmd:
        raise ValueError("Command cannot be empty")

    base_cmd = cmd[0]
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

    password_input = (sudo_password + "\n").encode()
    stdout, stderr = await proc.communicate(input=password_input)

    output = ""
    if stdout:
        output += stdout.decode(errors="replace")
    if stderr:
        output += stderr.decode(errors="replace")

    return output

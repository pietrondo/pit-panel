"""Core security services."""

import contextlib
import subprocess

from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.security.ipban import ban_ip


def _run_cmd(cmd: list[str], timeout: int = 10, input: str | None = None) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, input=input
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception:
        return "unavailable"


async def _firewall_status() -> dict:
    ufw = _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
    if "not found" in ufw.lower() or "command not found" in ufw.lower():
        install = _run_cmd(
            ["sudo", "-n", "apt-get", "install", "-y", "ufw"], timeout=60
        )
        if "Setting up ufw" in install or "ufw is already" in install:
            _run_cmd(["sudo", "-n", "ufw", "--force", "enable"])
            for port in ["22/tcp", "80/tcp", "443/tcp", "8080/tcp"]:
                _run_cmd(["sudo", "-n", "ufw", "allow", port])
            ufw = _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
    active = "Status: active" in ufw
    if not active and "Status: inactive" in ufw:
        _run_cmd(["sudo", "-n", "ufw", "--force", "enable"])
        for port in ["22/tcp", "80/tcp", "443/tcp", "8080/tcp"]:
            _run_cmd(["sudo", "-n", "ufw", "allow", port])
        ufw = _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
        active = "Status: active" in ufw
    rules = []
    for line in ufw.split("\n"):
        stripped = line.strip()
        if stripped and stripped != "Status: active" and "sudo:" not in stripped:
            rules.append(stripped)
    return {"active": active, "rules": rules[:20]}


async def _fail2ban_status() -> dict:
    status = _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
    if "not found" in status.lower() or "command not found" in status.lower():
        install = _run_cmd(
            ["sudo", "-n", "apt-get", "install", "-y", "fail2ban"], timeout=60
        )
        if "Setting up fail2ban" in install or "fail2ban is already" in install:
            _ensure_fail2ban_jails()
            status = _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
    jails = []
    active = "|- Number of jail:" in status
    if "sudo:" in status and "|- Number of jail:" not in status:
        return {"active": False, "jails": []}
    for line in status.split("\n"):
        stripped = line.strip().lstrip("`")
        if stripped.startswith("- ") and "Jail list:" not in stripped:
            jails.append(stripped.lstrip("- "))
    if active and not jails:
        _ensure_fail2ban_jails()
        status = _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
        for line in status.split("\n"):
            stripped = line.strip().lstrip("`")
            if stripped.startswith("- ") and "Jail list:" not in stripped:
                jails.append(stripped.lstrip("- "))
    return {"active": active, "jails": jails}


JAIL_DEFAULTS = {
    "sshd": {
        "port": "ssh",
        "filter": "sshd",
        "logpath": "/var/log/auth.log",
        "maxretry": "5",
        "bantime": "3600",
    },
    "sshd-ddos": {
        "port": "ssh",
        "filter": "sshd-ddos",
        "logpath": "/var/log/auth.log",
        "maxretry": "3",
        "bantime": "7200",
    },
    "nginx-http-auth": {
        "port": "http,https",
        "filter": "nginx-http-auth",
        "logpath": "/var/log/nginx/error.log",
        "maxretry": "5",
        "bantime": "3600",
    },
    "apache-auth": {
        "port": "http,https",
        "filter": "apache-auth",
        "logpath": "/var/log/apache2/error.log",
        "maxretry": "5",
        "bantime": "3600",
    },
    "postfix": {
        "port": "smtp,ssmtp",
        "filter": "postfix",
        "logpath": "/var/log/mail.log",
        "maxretry": "5",
        "bantime": "3600",
    },
}


def _ensure_fail2ban_jails():
    lines = []
    for jail, cfg in JAIL_DEFAULTS.items():
        lines.append(f"[{jail}]")
        for k, v in cfg.items():
            lines.append(f"{k} = {v}")
        lines.append("")
    content = "\n".join(lines)
    _run_cmd(
        ["sudo", "-n", "tee", "/etc/fail2ban/jail.local"],
        timeout=10,
        input=content,
    )
    _run_cmd(["sudo", "-n", "systemctl", "restart", "fail2ban"])




async def ban_ip_address(
    db: AsyncSession, ip: str, reason: str, duration_minutes: int = 60
) -> bool:
    """Ban an IP address at both the database and system (UFW) level."""
    # System level ban
    with contextlib.suppress(Exception):
        _run_cmd(["sudo", "-n", "ufw", "deny", "from", ip])

    # Database level ban
    return await ban_ip(db, ip, reason, duration_minutes)

async def unban_ip_address(db: AsyncSession, ip: str, user_id: int | None = None) -> bool:
    """Unban an IP address at both the database and system (UFW) level."""
    from pit_panel.security.ipban import unban_ip

    # System level unban
    with contextlib.suppress(Exception):
        _run_cmd(["sudo", "-n", "ufw", "delete", "deny", "from", ip])

    # Database level unban
    return await unban_ip(db, ip, user_id)

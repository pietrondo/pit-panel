"""Core security services."""

import contextlib
import re
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.sudo_ops import run_cmd
from pit_panel.security.ipban import ban_ip


async def _run_cmd(cmd: list[str], timeout: int = 10, input: str | None = None) -> str:
    res = await run_cmd(cmd, timeout=timeout, input=input)
    if res.returncode == -1:
        return "unavailable"
    return res.stdout.strip() or res.stderr.strip()


def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


async def _detect_ssh_port() -> int:
    path = "/etc/ssh/sshd_config"
    content = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except PermissionError:
        content = await _run_cmd(["sudo", "-n", "cat", path])
    except Exception:
        return 22

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        m = re.match(r"^Port\s+(\d+)", line, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return 22


def _parse_ufw_rules(ufw_output: str) -> list[dict[str, Any]]:
    rules = []
    pattern = re.compile(
        r"^\[\s*(\d+)\]\s+(.*?)\s{2,}(ALLOW IN|DENY IN|LIMIT IN|ALLOW OUT|DENY OUT|LIMIT OUT|ALLOW|DENY|LIMIT)\s{2,}(.*)$",  # noqa: E501
        re.IGNORECASE,
    )
    for line in ufw_output.splitlines():
        line = line.strip()
        m = pattern.match(line)
        if m:
            index = int(m.group(1))
            port_proto = m.group(2).strip()
            action = m.group(3).strip()
            source = m.group(4).strip()

            protocol = "any"
            port = port_proto
            if "/" in port_proto:
                parts = port_proto.split("/")
                port = parts[0].strip()
                proto_part = parts[1].strip()
                if "tcp" in proto_part.lower():
                    protocol = "tcp"
                elif "udp" in proto_part.lower():
                    protocol = "udp"

            rules.append({
                "index": index,
                "port": port,
                "protocol": protocol,
                "action": action,
                "source": source,
                "raw": line
            })
    return rules


async def _firewall_status() -> dict[str, Any]:
    ufw = await _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
    if "not found" in ufw.lower() or "command not found" in ufw.lower():
        install = await _run_cmd(["sudo", "-n", "apt-get", "install", "-y", "ufw"], timeout=60)
        if "Setting up ufw" in install or "ufw is already" in install:
            await _run_cmd(["sudo", "-n", "ufw", "--force", "enable"])
            for port in ["22/tcp", "80/tcp", "443/tcp", "8080/tcp"]:
                await _run_cmd(["sudo", "-n", "ufw", "allow", port])
            ufw = await _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
    active = "Status: active" in ufw
    if not active and "Status: inactive" in ufw:
        await _run_cmd(["sudo", "-n", "ufw", "--force", "enable"])
        for port in ["22/tcp", "80/tcp", "443/tcp", "8080/tcp"]:
            await _run_cmd(["sudo", "-n", "ufw", "allow", port])
        ufw = await _run_cmd(["sudo", "-n", "ufw", "status", "numbered"])
        active = "Status: active" in ufw

    parsed_rules = _parse_ufw_rules(ufw)
    return {"active": active, "rules": parsed_rules[:20]}


async def _add_ufw_rule(
    port: str | None, protocol: str, action: str, source_ip: str | None = None
) -> bool:  # noqa: E501
    cmd = ["sudo", "-n", "ufw"]
    action_lower = action.lower()
    if port in (None, "any"):
        if source_ip:
            cmd += [action_lower, "from", source_ip]
        else:
            return False
    else:
        if source_ip:
            cmd += [action_lower, "from", source_ip, "to", "any", "port", port]
            if protocol and protocol.lower() != "any":
                cmd += ["proto", protocol.lower()]
        else:
            rule = port
            if protocol and protocol.lower() != "any":
                rule = f"{port}/{protocol.lower()}"
            cmd += [action_lower, rule]
    res = await _run_cmd(cmd)
    await _run_cmd(["sudo", "-n", "ufw", "reload"])
    return res != "unavailable"


async def _delete_ufw_rule(index: int, client_ip: str, ssh_port: int) -> bool:
    status = await _firewall_status()
    rule = None
    for r in status["rules"]:
        if r["index"] == index:
            rule = r
            break
    if not rule:
        raise ValueError(f"Rule with index {index} not found")

    if (
        (rule["port"] == str(ssh_port) or rule["port"].lower() == "ssh")
        and "allow" in rule["action"].lower()
    ):  # noqa: E501
        raise ValueError("Cannot delete active SSH rule")
    if rule["source"] == client_ip and "allow" in rule["action"].lower():
        raise ValueError("Cannot delete active client IP bypass rule")

    res = await _run_cmd(["sudo", "-n", "ufw", "--force", "delete", str(index)])
    await _run_cmd(["sudo", "-n", "ufw", "reload"])
    return res != "unavailable"


async def _enable_ufw(client_ip: str, ssh_port: int) -> bool:
    await _add_ufw_rule(str(ssh_port), "tcp", "allow")
    await _add_ufw_rule("any", "any", "allow", source_ip=client_ip)
    res = await _run_cmd(["sudo", "-n", "ufw", "--force", "enable"])
    return res != "unavailable"


async def _disable_ufw() -> bool:
    res = await _run_cmd(["sudo", "-n", "ufw", "disable"])
    return res != "unavailable"


async def _fail2ban_status() -> dict[str, Any]:
    status = await _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
    if "not found" in status.lower() or "command not found" in status.lower():
        install = await _run_cmd(["sudo", "-n", "apt-get", "install", "-y", "fail2ban"], timeout=60)
        if "Setting up fail2ban" in install or "fail2ban is already" in install:
            await _ensure_fail2ban_jails()
            status = await _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
    jails = []
    active = "|- Number of jail:" in status
    if "sudo:" in status and "|- Number of jail:" not in status:
        return {"active": False, "jails": []}
    for line in status.split("\n"):
        stripped = line.strip().lstrip("`")
        if stripped.startswith("- ") and "Jail list:" not in stripped:
            jails.append(stripped.lstrip("- "))
    if active and not jails:
        await _ensure_fail2ban_jails()
        status = await _run_cmd(["sudo", "-n", "fail2ban-client", "status"])
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


async def _ensure_fail2ban_jails():
    lines = []
    for jail, cfg in JAIL_DEFAULTS.items():
        lines.append(f"[{jail}]")
        for k, v in cfg.items():
            lines.append(f"{k} = {v}")
        lines.append("")
    content = "\n".join(lines)
    await _run_cmd(
        ["sudo", "-n", "tee", "/etc/fail2ban/jail.local"],
        timeout=10,
        input=content,
    )
    await _run_cmd(["sudo", "-n", "/usr/bin/systemctl", "restart", "fail2ban"])


async def _fail2ban_jail_banned(jail: str) -> list[dict[str, str]]:
    out = await _run_cmd(["sudo", "-n", "/usr/bin/fail2ban-client", "status", jail], timeout=10)
    ips = []
    for line in out.split("\n"):
        line = line.strip()
        if "Banned IP list:" in line:
            raw = line.split(":", 1)[1].strip()
            if raw and raw != "None":
                for ip in raw.split():
                    ips.append({"ip": ip.strip()})
            break
    return ips


async def _fail2ban_unban(jail: str, ip: str) -> bool:
    out = await _run_cmd(["sudo", "-n", "fail2ban-client", "set", jail, "unbanip", ip], timeout=10)
    return ip not in out


async def ban_ip_address(
    db: AsyncSession, ip: str, reason: str, duration_minutes: int = 60
) -> bool:
    """Ban an IP address at both the database and system (UFW) level."""
    # System level ban
    with contextlib.suppress(Exception):
        await _run_cmd(["sudo", "-n", "ufw", "deny", "from", ip])

    # Database level ban
    return await ban_ip(db, ip, reason, duration_minutes)


async def unban_ip_address(db: AsyncSession, ip: str, user_id: int | None = None) -> bool:
    """Unban an IP address at both the database and system (UFW) level."""
    from pit_panel.security.ipban import unban_ip

    # System level unban
    with contextlib.suppress(Exception):
        await _run_cmd(["sudo", "-n", "ufw", "delete", "deny", "from", ip])

    # Database level unban
    return await unban_ip(db, ip, user_id)


async def _get_jail_config(jail: str) -> dict[str, Any]:
    bantime = await _run_cmd(["sudo", "-n", "fail2ban-client", "get", jail, "bantime"])
    findtime = await _run_cmd(["sudo", "-n", "fail2ban-client", "get", jail, "findtime"])
    maxretry = await _run_cmd(["sudo", "-n", "fail2ban-client", "get", jail, "maxretry"])

    def parse_val(val, default):
        try:
            return int(val.strip())
        except Exception:
            return int(default)

    defaults = JAIL_DEFAULTS.get(jail, {"bantime": 600, "findtime": 600, "maxretry": 5})
    return {
        "bantime": parse_val(bantime, defaults.get("bantime", 600)),
        "findtime": parse_val(findtime, defaults.get("findtime", 600)),
        "maxretry": parse_val(maxretry, defaults.get("maxretry", 5)),
    }


async def _save_jail_config(jail: str, bantime: Any, findtime: Any, maxretry: Any) -> bool:
    import configparser
    from io import StringIO

    try:
        b = int(bantime)
        f = int(findtime)
        m = int(maxretry)
        if b <= 0 or f <= 0 or m <= 0:
            raise ValueError()
    except Exception as e:
        raise ValueError("Parameters must be positive integers") from e

    path = "/etc/fail2ban/jail.d/pit-panel-overrides.local"
    content = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as file:
            content = file.read()
    except PermissionError:
        content = await _run_cmd(["sudo", "-n", "cat", path])
    except Exception:
        pass

    config = configparser.ConfigParser()
    if "[" in content:
        config.read_string(content)

    if not config.has_section(jail):
        config.add_section(jail)
    config.set(jail, "bantime", str(b))
    config.set(jail, "findtime", str(f))
    config.set(jail, "maxretry", str(m))

    out = StringIO()
    config.write(out)
    new_content = out.getvalue()

    write_res = await _run_cmd(
        ["sudo", "-n", "tee", path],
        timeout=10,
        input=new_content
    )
    if write_res == "unavailable":
        return False

    reload_res = await _run_cmd(["sudo", "-n", "fail2ban-client", "reload"])
    return reload_res != "unavailable"


def _parse_lynis_report(dat_content: str) -> dict[str, Any]:
    from datetime import UTC, datetime
    hardening_index = 0
    warnings = []
    suggestions = []

    for line in dat_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            parts = line.split("=", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            if key == "hardening_index":
                with contextlib.suppress(Exception):
                    hardening_index = int(val)
            elif key == "warning[]":
                warnings.append(val)
            elif key == "suggestion[]":
                suggestions.append(val)

    return {
        "hardening_index": hardening_index,
        "scan_timestamp": datetime.now(UTC).isoformat(),
        "warnings": warnings,
        "suggestions": suggestions
    }


async def run_lynis_audit() -> dict[str, Any]:
    import json
    import os
    import shutil

    lynis_path = shutil.which("lynis")
    if not lynis_path:
        await _run_cmd(["sudo", "-n", "apt-get", "install", "-y", "lynis"], timeout=60)
        lynis_path = shutil.which("lynis")
        if not lynis_path:
            return {
                "status": "failed",
                "error": "Lynis binary not found and auto-installation failed."
            }

    await _run_cmd(["sudo", "-n", "lynis", "audit", "system", "--quick"], timeout=180)

    dat_path = "/var/log/lynis-report.dat"
    dat_content = ""
    try:
        with open(dat_path, encoding="utf-8", errors="replace") as f:
            dat_content = f.read()
    except PermissionError:
        dat_content = await _run_cmd(["sudo", "-n", "cat", dat_path])
    except Exception as e:
        return {
            "status": "failed",
            "error": f"Failed to read Lynis report file: {e}"
        }

    report = _parse_lynis_report(dat_content)

    cache_dir = "/var/lib/pit-panel"
    cache_path = f"{cache_dir}/lynis_last_report.json"
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    except Exception:
        try:
            content_str = json.dumps(report, indent=2)
            await _run_cmd(["sudo", "-n", "tee", cache_path], input=content_str)
        except Exception:
            pass

    return report

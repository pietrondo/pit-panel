"""Anti-DDoS emergency routes — panic button, status, disable."""

import asyncio
import contextlib

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.sudo_ops import run_cmd
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin

router = APIRouter()

DDOS_CHAIN = "PIT_DDOS_SHIELD"

_SUDOERS_LINES = [
    "pit-panel ALL=(root) NOPASSWD: /usr/sbin/iptables *",
    "pit-panel ALL=(root) NOPASSWD: /usr/sbin/ss *",
    "pit-panel ALL=(root) NOPASSWD: /usr/bin/ss *",
    "pit-panel ALL=(root) NOPASSWD: /usr/bin/fail2ban-client start *",
]

_SUDOERS_FIX_CMD = (
    "sudo tee -a /etc/sudoers.d/pit-panel <<'EOF'\n" + "\n".join(_SUDOERS_LINES) + "\nEOF"
)


async def _ensure_sudoers() -> bool:
    res = await run_cmd(["sudo", "-n", "iptables", "-L", "-n"], timeout=5)
    if res.returncode == 0:
        return True

    from pit_panel.config import get_settings

    settings = get_settings()
    sudo_password = settings.sudo_password.strip() if settings.sudo_password else None
    if not sudo_password:
        return False

    import asyncio

    payload = "\n".join(_SUDOERS_LINES) + "\n"
    input_data = (sudo_password + "\n" + payload).encode()
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-S",
            "-p",
            "",
            "tee",
            "-a",
            "/etc/sudoers.d/pit-panel",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(input_data), timeout=10)
    except Exception:
        return False

    res = await run_cmd(["sudo", "-n", "iptables", "-L", "-n"], timeout=5)
    return res.returncode == 0


_IPTABLES_RULES: list[list[str]] = [
    ["-N", DDOS_CHAIN],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--syn",
        "-m",
        "limit",
        "--limit",
        "2/s",
        "--limit-burst",
        "5",
        "-j",
        "RETURN",
    ],
    ["-A", DDOS_CHAIN, "-p", "tcp", "--syn", "-j", "DROP"],
    ["-A", DDOS_CHAIN, "-p", "tcp", "--tcp-flags", "ALL", "NONE", "-j", "DROP"],
    ["-A", DDOS_CHAIN, "-p", "tcp", "--tcp-flags", "ALL", "FIN,URG,PSH", "-j", "DROP"],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--tcp-flags",
        "ALL",
        "SYN,RST,ACK,FIN,URG",
        "-j",
        "DROP",
    ],
    ["-A", DDOS_CHAIN, "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN,RST", "-j", "DROP"],
    ["-A", DDOS_CHAIN, "-p", "tcp", "--tcp-flags", "SYN,FIN", "SYN,FIN", "-j", "DROP"],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "icmp",
        "--icmp-type",
        "echo-request",
        "-m",
        "limit",
        "--limit",
        "1/s",
        "--limit-burst",
        "4",
        "-j",
        "RETURN",
    ],
    ["-A", DDOS_CHAIN, "-p", "icmp", "--icmp-type", "echo-request", "-j", "DROP"],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--dport",
        "80",
        "-m",
        "connlimit",
        "--connlimit-above",
        "30",
        "--connlimit-mask",
        "32",
        "-j",
        "DROP",
    ],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--dport",
        "443",
        "-m",
        "connlimit",
        "--connlimit-above",
        "30",
        "--connlimit-mask",
        "32",
        "-j",
        "DROP",
    ],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--dport",
        "80",
        "-m",
        "recent",
        "--set",
        "--name",
        "HTTP_FLOOD",
    ],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--dport",
        "80",
        "-m",
        "recent",
        "--update",
        "--seconds",
        "10",
        "--hitcount",
        "50",
        "--name",
        "HTTP_FLOOD",
        "-j",
        "DROP",
    ],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--dport",
        "443",
        "-m",
        "recent",
        "--set",
        "--name",
        "HTTPS_FLOOD",
    ],
    [
        "-A",
        DDOS_CHAIN,
        "-p",
        "tcp",
        "--dport",
        "443",
        "-m",
        "recent",
        "--update",
        "--seconds",
        "10",
        "--hitcount",
        "50",
        "--name",
        "HTTPS_FLOOD",
        "-j",
        "DROP",
    ],
    ["-A", DDOS_CHAIN, "-j", "RETURN"],
]


async def _iptables(args: list[str], timeout: int = 10) -> bool:
    res = await run_cmd(["sudo", "-n", "iptables"] + args, timeout=timeout)
    return res.returncode == 0


async def _is_shield_active() -> bool:
    res = await run_cmd(["sudo", "-n", "iptables", "-L", DDOS_CHAIN, "-n"], timeout=5)
    return res.returncode == 0 and "No such file" not in res.stderr


async def _enable_shield() -> list[str]:
    results: list[str] = []
    for rule in _IPTABLES_RULES:
        if rule[0] == "-N":
            await _iptables(["-F", DDOS_CHAIN])
            await _iptables(["-X", DDOS_CHAIN])
        ok = await _iptables(rule)
        if not ok and rule[0] != "-N":
            results.append(f"⚠️ {' '.join(rule[:4])}")

    await _iptables(["-I", "INPUT", "1", "-j", DDOS_CHAIN])

    for port in ("80", "443"):
        await _iptables(
            [
                "-A",
                DDOS_CHAIN,
                "-p",
                "tcp",
                "--dport",
                port,
                "-m",
                "state",
                "--state",
                "ESTABLISHED",
                "-j",
                "RETURN",
            ]
        )

    return results


async def _disable_shield() -> None:
    await _iptables(["-D", "INPUT", "-j", DDOS_CHAIN])
    await _iptables(["-F", DDOS_CHAIN])
    await _iptables(["-X", DDOS_CHAIN])


@router.get("/security/ddos/status", response_class=HTMLResponse)
async def security_ddos_status(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    active = await _is_shield_active()
    if active:
        return HTMLResponse(
            '<span class="px-2 py-0.5 rounded-full text-xs font-medium '
            'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">'
            "🛡️ Protezione ATTIVA</span>"
        )
    return HTMLResponse(
        '<span class="px-2 py-0.5 rounded-full text-xs font-medium '
        'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400">'
        "⚪ Non attiva</span>"
    )


@router.post("/security/ddos/enable", response_class=HTMLResponse)
async def security_ddos_enable(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    if not await _ensure_sudoers():
        import html as html_mod

        return HTMLResponse(
            '<div class="text-xs space-y-2">'
            '<p class="text-red-600 font-medium">❌ iptables non è nei sudoers.</p>'
            '<p class="text-gray-600">Esegui questo comando via SSH come root:</p>'
            f'<pre class="p-2 bg-gray-100 dark:bg-gray-800 rounded text-[10px] overflow-x-auto">'
            f"{html_mod.escape(_SUDOERS_FIX_CMD)}</pre>"
            "</div>"
        )

    errors = await _enable_shield()

    async def _enable_f2b_ddos():
        await run_cmd(["sudo", "-n", "fail2ban-client", "start", "sshd-ddos"], timeout=10)

    with contextlib.suppress(Exception):
        await asyncio.wait_for(_enable_f2b_ddos(), timeout=12)

    if errors:
        return HTMLResponse(
            '<div class="text-xs space-y-1">'
            '<p class="text-green-600 font-medium">✅ Shield attivato con avvisi:</p>'
            + "".join(f'<p class="text-yellow-600">{e}</p>' for e in errors)
            + "</div>"
        )
    return HTMLResponse(
        '<p class="text-green-600 text-xs font-medium">'
        "✅ Anti-DDoS Shield attivato! Regole iptables + fail2ban sshd-ddos applicate.</p>"
    )


@router.post("/security/ddos/disable", response_class=HTMLResponse)
async def security_ddos_disable(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    await _disable_shield()
    return HTMLResponse(
        '<p class="text-yellow-600 text-xs font-medium">'
        "⚠️ Shield rimosso. Il traffico non è più filtrato dalle regole anti-DDoS.</p>"
    )


@router.post("/security/ddos/block-ip", response_class=HTMLResponse)
async def security_ddos_block_ip(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    form = await request.form()
    ip = str(form.get("ip", "")).strip()

    import ipaddress as ipmod

    try:
        ipmod.ip_network(ip, strict=False)
    except ValueError:
        return HTMLResponse(
            '<span class="text-red-600 text-xs">❌ IP non valido</span>', status_code=400
        )

    ok = await _iptables(["-I", "INPUT", "1", "-s", ip, "-j", "DROP"])
    if ok:
        return HTMLResponse(
            f'<span class="text-green-600 text-xs">✅ {ip} bloccato a livello kernel</span>'
        )
    return HTMLResponse(f'<span class="text-red-600 text-xs">❌ Impossibile bloccare {ip}</span>')


@router.post("/security/ddos/unblock-ip", response_class=HTMLResponse)
async def security_ddos_unblock_ip(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    form = await request.form()
    ip = str(form.get("ip", "")).strip()

    import ipaddress as ipmod

    try:
        ipmod.ip_network(ip, strict=False)
    except ValueError:
        return HTMLResponse(
            '<span class="text-red-600 text-xs">❌ IP non valido</span>', status_code=400
        )

    ok = await _iptables(["-D", "INPUT", "-s", ip, "-j", "DROP"])
    if ok:
        return HTMLResponse(f'<span class="text-green-600 text-xs">✅ {ip} sbloccato</span>')
    return HTMLResponse(f'<span class="text-red-600 text-xs">❌ Regola non trovata per {ip}</span>')


@router.get("/security/ddos/top-connections", response_class=HTMLResponse)
async def security_ddos_top_connections(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    res = await run_cmd(
        ["sudo", "-n", "ss", "-tn", "state", "established"],
        timeout=10,
    )
    if res.returncode != 0:
        res = await run_cmd(["ss", "-tn"], timeout=10)

    ip_counts: dict[str, int] = {}
    for line in res.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 5:
            peer = parts[4]
            ip = peer.rsplit(":", 1)[0] if ":" in peer else peer
            if ip and ip not in ("127.0.0.1", "::1"):
                ip_counts[ip] = ip_counts.get(ip, 0) + 1

    top = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:15]

    if not top:
        return HTMLResponse(
            '<p class="text-xs text-gray-500">Nessuna connessione attiva rilevata.</p>'
        )

    rows = ""
    for ip, count in top:
        danger = "text-red-600 font-bold" if count > 20 else "text-gray-900 dark:text-white"
        rows += (
            f'<div class="flex items-center justify-between py-1.5 px-3 '
            f'bg-gray-50 dark:bg-gray-800/50 rounded-lg">'
            f'<span class="font-mono text-xs {danger}">{ip}</span>'
            f'<div class="flex items-center gap-2">'
            f'<span class="text-xs text-gray-500">{count} conn</span>'
            f'<button class="btn-ghost text-xs text-red-600" '
            f'hx-post="/security/ddos/block-ip" '
            f'hx-vals=\'{{"ip":"{ip}"}}\' '
            f'hx-target="#ddos-block-result" '
            f'hx-swap="innerHTML">🚫 Blocca</button>'
            f"</div></div>"
        )

    return HTMLResponse(f'<div class="space-y-1.5">{rows}</div>')


@router.post("/security/protect-all", response_class=HTMLResponse)
async def security_protect_all(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    from pit_panel.core.security import _detect_ssh_port, _enable_ufw, _get_client_ip

    results: list[str] = []

    client_ip = _get_client_ip(request)
    ssh_port = await _detect_ssh_port()
    fw_ok = await _enable_ufw(client_ip, ssh_port)
    results.append("✅ Firewall UFW attivato" if fw_ok else "⚠️ Firewall: errore")

    for jail in ("sshd", "sshd-ddos"):
        r = await run_cmd(["sudo", "-n", "fail2ban-client", "start", jail], timeout=10)
        if r.returncode == 0:
            results.append(f"✅ Fail2ban: {jail} attivo")
        else:
            results.append(f"⚠️ Fail2ban: {jail} non disponibile")

    if await _ensure_sudoers():
        errors = await _enable_shield()
        if errors:
            results.append("✅ Anti-DDoS Shield attivato (con avvisi)")
        else:
            results.append("✅ Anti-DDoS Shield attivato")
    else:
        results.append("⚠️ Anti-DDoS: iptables non nei sudoers")

    html = "".join(f'<p class="text-xs">{r}</p>' for r in results)
    return HTMLResponse(
        f'<div class="space-y-1 p-3 bg-green-50 dark:bg-green-900/10 '
        f'border border-green-200 dark:border-green-800 rounded-lg">{html}</div>'
    )

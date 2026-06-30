"""Routes for system management requiring sudo password."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.sudo_ops import run_sudo
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()

SERVICES = [
    ("pit-panel", "Pit Panel"),
    ("caddy", "Caddy"),
    ("docker", "Docker"),
    ("fail2ban", "Fail2Ban"),
    ("ssh", "SSH"),
    ("nginx", "Nginx"),
]

STATIC_COMMANDS = {
    "restart_caddy": ["/usr/bin/systemctl", "restart", "caddy"],
    "restart_panel": ["/usr/bin/systemctl", "restart", "pit-panel"],
    "apt_update": ["/usr/bin/apt-get", "update", "-q"],
    "apt_upgrade": ["/usr/bin/apt-get", "upgrade", "-y", "-q"],
    "apt_dist_upgrade": ["/usr/bin/apt-get", "dist-upgrade", "-y", "-q"],
    "apt_list_upgradable": ["/usr/bin/apt", "list", "--upgradable", "-q"],
    "df": ["/usr/bin/df", "-h"],
    "free": ["/usr/bin/free", "-m"],
    "uptime": ["/usr/bin/uptime"],
    "journal_panel": ["/usr/bin/journalctl", "-u", "pit-panel", "-n", "100", "--no-pager"],
    "journal_caddy": ["/usr/bin/journalctl", "-u", "caddy", "-n", "100", "--no-pager"],
    "journal_docker": ["/usr/bin/journalctl", "-u", "docker", "-n", "100", "--no-pager"],
    "journal_ssh": ["/usr/bin/journalctl", "-u", "ssh", "-n", "50", "--no-pager"],
    "docker_ps": ["/usr/bin/docker", "ps"],
    "reboot": ["/usr/sbin/reboot"],
}


def _resolve_cmd(action: str) -> list[str] | None:
    if action in STATIC_COMMANDS:
        return STATIC_COMMANDS[action]
    if action.startswith("service_restart_"):
        return ["/usr/bin/systemctl", "restart", action.removeprefix("service_restart_")]
    if action.startswith("service_stop_"):
        return ["/usr/bin/systemctl", "stop", action.removeprefix("service_stop_")]
    if action.startswith("service_start_"):
        return ["/usr/bin/systemctl", "start", action.removeprefix("service_start_")]
    if action.startswith("journal_"):
        svc_name = action.removeprefix("journal_")
        return ["/usr/bin/journalctl", "-u", svc_name, "-n", "100", "--no-pager"]
    return None


@router.get("/system/manage", response_class=HTMLResponse)
async def system_manage_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render("system_manage.html", user=user, settings=get_settings())


@router.post("/system/manage/action", response_class=HTMLResponse)
async def system_manage_action(
    request: Request,
    action: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    sudo_password = request.app.state.settings.sudo_password.strip()
    if not sudo_password:
        return HTMLResponse(
            "<span class='text-red-500 font-semibold'>"
            "Error: sudo_password is not configured in config.toml.</span>"
        )

    cmd = _resolve_cmd(action)
    if cmd is None:
        return HTMLResponse(f"Unknown action: {action}", status_code=400)

    try:
        output = await run_sudo(cmd, sudo_password)
        if "incorrect password attempt" in output or "no password was provided" in output:
            import getpass

            output += (
                f"\n\n[pit-panel Note] Sudo authentication failed. "
                f"Running as '{getpass.getuser()}'. "
                f"Check 'sudo_password' in config.toml."
            )
    except Exception as e:
        import getpass

        output = f"Error running sudo as '{getpass.getuser()}': {str(e)}"

    return HTMLResponse(output)


@router.get("/system/manage/services", response_class=HTMLResponse)
async def system_manage_services(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return HTMLResponse("")

    sudo_password = request.app.state.settings.sudo_password.strip()
    if not sudo_password:
        return HTMLResponse('<span class="text-red-500">sudo_password not configured</span>')

    lines = []
    for svc, label in SERVICES:
        try:
            result = await run_sudo(["/usr/bin/systemctl", "is-active", svc], sudo_password)
            status = result.strip()
        except Exception:
            status = "unknown"

        badges = {
            "active": "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
            "inactive": "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
            "dead": "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        }
        badge = badges.get(status, "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400")
        is_active = status == "active"

        dot = "bg-green-500" if is_active else "bg-red-500"
        status_dot = f'<span class="w-2 h-2 rounded-full {dot}"></span>'
        status_badge = f'<span class="px-2 py-0.5 rounded-full text-xs font-medium {badge}">{"●" if is_active else "○"} {status}</span>'  # noqa: E501

        restart_btn = (
            f'<button class="btn-ghost text-xs" '
            f'hx-post="/system/manage/action" '
            f'hx-vals=\'{{"action": "service_restart_{svc}"}}\' '
            f'hx-target="#result" '
            f"hx-on::before-request=\"this.disabled=true;this.innerText='...'\" "
            f"hx-on::after-request=\"this.disabled=false;this.innerText='Restart'\""
            f">Restart</button>"
        )
        logs_btn = (
            f'<button class="btn-ghost text-xs" '
            f'hx-post="/system/manage/action" '
            f'hx-vals=\'{{"action": "journal_{svc}"}}\' '
            f'hx-target="#result">Logs</button>'
        )

        card_class = "flex items-center justify-between p-3 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700"  # noqa: E501
        lines.append(f"""
        <div class="{card_class}">
            <div class="flex items-center gap-3">
                {status_dot}
                <span class="font-medium text-sm text-gray-900 dark:text-white">{label}</span>
                <span class="text-xs font-mono text-gray-500">{svc}</span>
            </div>
            <div class="flex items-center gap-2">
                {status_badge}
                {restart_btn}
                {logs_btn}
            </div>
        </div>""")

    return HTMLResponse("".join(lines))

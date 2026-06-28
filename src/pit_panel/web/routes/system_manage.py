"""Routes for system management requiring sudo password."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.core.sudo_ops import run_sudo
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

router = APIRouter()


@router.get("/system/manage", response_class=HTMLResponse)
async def system_manage_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    return render("system_manage.html", user=user)


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
            "Error: sudo_password is not configured in config.toml.<br>"
            "Please configure the 'sudo_password' field under the root level "
            "in /etc/pit-panel/config.toml and restart the pit-panel service.</span>"
        )

    # Map actions to commands
    commands = {
        "restart_caddy": ["systemctl", "restart", "caddy"],
        "restart_panel": ["systemctl", "restart", "pit-panel"],
        "apt_update": ["apt-get", "update"],
        "df": ["df", "-h"],
        "free": ["free", "-m"],
        "journal_panel": ["journalctl", "-u", "pit-panel", "-n", "50", "--no-pager"],
        "reboot": ["reboot"],
    }

    if action not in commands:
        return HTMLResponse(f"Unknown action: {action}", status_code=400)

    cmd = commands[action]

    try:
        output = await run_sudo(cmd, sudo_password)
        if "incorrect password attempt" in output or "no password was provided" in output:
            import getpass
            output += (
                f"\n\n[pit-panel Note] Sudo authentication failed. The panel is currently running "
                f"as system user '{getpass.getuser()}'.\n"
                f"Please check that 'sudo_password' in config.toml "
                f"matches the password of the '{getpass.getuser()}' system user."
            )
    except Exception as e:
        import getpass
        output = f"Error running sudo command as user '{getpass.getuser()}': {str(e)}"

    return HTMLResponse(output)

# Debian System Management Spec

We need a new page for system administration (System Management).
Unlike the old `/system` upgrade page which relied on NOPASSWD sudoers entries, this new implementation MUST require the user to provide their sudo password via the web interface.

## 1. `config.py` Additions
Add `sudo_password: str = ""` to `Settings`. This will be used to run sudo commands. (Note: in reality this should be stored securely or requested on demand, but for this spec, store it in Settings).

## 2. Core Service `src/pit_panel/core/sudo_ops.py`
Create a module `sudo_ops.py` with an async function `run_sudo(cmd: list[str], sudo_password: str) -> str`.
- It should run the given command with `sudo -S -p '' <cmd>`.
- Pass the `sudo_password` followed by a newline into `stdin`.
- Ensure it restricts the allowed commands to a strict whitelist: `["systemctl", "apt-get", "journalctl", "df", "free", "reboot"]`. If the first element of `cmd` is not in this list, raise ValueError.
- Return `stdout + stderr`.

## 3. Web Routes `src/pit_panel/web/routes/system_manage.py`
Create `system_manage.py`:
- `GET /system/manage`: Return the `system_manage.html` template.
- `POST /system/manage/action`: Accept form data with `action` (e.g. "restart_caddy", "apt_update", "reboot") and use `run_sudo` to execute the appropriate commands. Return an HTMX fragment or redirect back. Actions needed:
  - `restart_caddy`: `systemctl restart caddy`
  - `restart_panel`: `systemctl restart pit-panel`
  - `apt_update`: `apt-get update`
  - `df`: `df -h`
  - `free`: `free -m`
  - `journal_panel`: `journalctl -u pit-panel -n 50 --no-pager`
  - `reboot`: `reboot` (requires double confirm in UI, but handled in backend just by running the command)

Remember to register `system_manage_router` in `src/pit_panel/web/routes/__init__.py` and `app.py`.

## 4. UI `templates/system_manage.html`
Create `src/pit_panel/web/templates/system_manage.html`.
- Use a tabbed layout (Alpine.js or just standard HTML with anchor links):
  - Services: Buttons to restart Caddy and Pit-Panel.
  - Updates: Button to run apt-get update.
  - Resources: Buttons to fetch disk (df) and memory (free) info.
  - Logs: Button to fetch pit-panel journal.
  - Reboot: A button that says "Reboot System". It MUST have a double confirmation (e.g. `onsubmit="return confirm('Are you really sure you want to REBOOT?');"` or Alpine modal).
- Results of commands (like df, free, logs) should be displayed in a `<pre>` block using HTMX (`hx-post="/system/manage/action" hx-target="#result"`).

## 5. Tests
Write tests in `tests/unit/test_system_manage.py`.
Mock `subprocess.create_subprocess_exec` or `run_sudo` to verify that the correct commands are executed when the endpoints are called, and the whitelist is enforced.

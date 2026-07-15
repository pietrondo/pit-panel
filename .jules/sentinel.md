## 2026-07-13 - [Escape Command Output in System Manage]
**Vulnerability:** System manage commands (`system_manage.py:system_manage_action`) output (`output`) is directly rendered in an HTMLResponse without HTML escaping.
**Learning:** Returning unescaped output from external commands (`run_sudo`) creates a Cross-Site Scripting (XSS) vulnerability if the command output can be influenced by attackers or contains unexpected HTML characters.
**Prevention:** Always use `html.escape` to sanitize the output of system commands before returning it in an HTMLResponse.

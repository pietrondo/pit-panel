# Proposal: Host Web Terminal and File Manager

## Intent
Provide admin users with a web-based file manager and host terminal directly within the panel for system operations.

## Scope

### In Scope
- Web page `/system/terminal` with xterm.js terminal interface.
- WebSocket endpoint `/system/terminal/ws` spawning the host terminal shell process (`powershell.exe` on Windows, `/bin/bash` or `sh` on Linux) running as the host process user.
- Web page `/system/file-manager` with full browse, view, edit, create, upload, and delete capabilities, defaulting to `/opt/pit-panel` as base directory.
- APIs for file operations: listing, reading, saving, creating, deleting, and uploading.
- Authentication: Enforce authenticated admin user check on all terminal and file manager routes/WebSockets.

### Out of Scope
- File system access outside the host system (e.g. remote cloud storage).
- SSH client connection to remote hosts (this is host-only).
- Non-admin user access to terminal/files.

## Capabilities

### New Capabilities
- `host-terminal`: Web-based terminal emulator connected to the host shell via WebSockets.
- `file-manager`: System-wide web file manager with browse, view, edit, create, upload, and delete capabilities.

### Modified Capabilities
None

## Approach
- Integrate xterm.js in frontend for terminal emulation, communicating over WebSocket connection to Python backend.
- Python backend uses `asyncio` subprocess to spawn and interact with the host shell (`powershell.exe` / `bash`), relaying input/output.
- File manager uses standard Python `os`/`pathlib` async-wrapped file operations or direct sync operations where appropriate to perform CRUD on files/directories.
- Protect all endpoints with existing admin authentication/session checks.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/pit_panel/web/app.py` | Modified | Register new routes and WebSocket endpoint |
| `src/pit_panel/web/routes/file_manager.py` | New | Implement file manager and terminal routes/endpoints |
| `src/pit_panel/web/templates/file_manager.html` | New | Template for browsing and managing files |
| `src/pit_panel/web/templates/system_terminal.html` | New | Template containing xterm.js terminal interface |
| `src/pit_panel/web/templates/base.html` | Modified | Add sidebar links to file manager and system terminal |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Shell injection / unauthorized execution | Medium | Enforce strict admin-only session validation; run terminal process as the host panel user without root escalation unless explicitly configured. |
| Path traversal in file manager | High | Validate all requested paths to ensure they resolve safely and reject access outside permitted/configured base directories if applicable. |

## Rollback Plan
Perform a git checkout/reset on modified files.

## Dependencies
- `xterm` / `xterm-addon-fit` frontend libraries via CDN.
- Python standard library dependencies (`os`, `asyncio`, etc.).

## Success Criteria
- [ ] Admin users can open `/system/terminal` and run shell commands in an interactive terminal.
- [ ] Admin users can browse, read, write, create, upload, and delete files starting from `/opt/pit-panel` via `/system/file-manager`.
- [ ] Non-authenticated or non-admin requests to these endpoints are rejected with a 401/403 or redirect to login.

# Design: Host Web Terminal and File Manager

This document details the architecture and implementation details for the web-based File Manager and host-level Web Terminal.

---

## Technical Approach

The implementation introduces interactive system management capabilities directly in the pit-panel. 
- **Web Terminal**: High-fidelity terminal emulation using `xterm.js` in the frontend, communicating over a WebSocket session with a Python backend subprocess running the native shell.
- **File Manager**: Web UI using Alpine.js for browsing, reading/writing, creating, deleting, and uploading files in permitted system paths. Strict validation guards against directory traversal using `Path.is_relative_to()`.

---

## Architecture Decisions

### Decision: Path Traversal and Access Isolation
- **Choice**: Limit file operations strictly to a list of allowed directory roots (`/opt/pit-panel`, `/etc/pit-panel`, `/var/lib/pit-panel`). Resolve paths fully via `Path.resolve()` to eliminate symlink and `..` traversal, checking via `target_path.is_relative_to(root)`.
- **Alternatives considered**: Wildcard matching or simple substring checks (e.g. containing `..`).
- **Rationale**: Substring checks are vulnerable to symlink traversal. Resolving paths with `is_relative_to()` ensures that the path points physically under an allowed root folder, offering bulletproof security.

### Decision: Subprocess Piping via asyncio
- **Choice**: Spawn the shell process via `asyncio.create_subprocess_exec` mapping `stdin/stdout` directly to WebSocket text/binary messages. Spawn `powershell.exe` on Windows and `/bin/bash` or `sh` on Linux.
- **Alternatives considered**: Spawn a full pseudo-terminal (PTY) using Python `pty` or `os.openpty`.
- **Rationale**: Python's `pty` library is Unix-only, making Windows cross-compatibility difficult. Spawning a standard subprocess via `asyncio` runs reliably on both OS platforms.

---

## Data Flow

### Terminal WebSocket Data Flow
```
Web Browser (xterm.js) ──(ws.send data)──→ FastAPI (/system/terminal/ws) ──(process.stdin.write)──→ Subprocess Shell
Web Browser (xterm.js) ←──(websocket.send)── FastAPI (/system/terminal/ws) ←──(read stdout/stderr)─── Subprocess Shell
```

### File Manager CRUD Flow
```
Browser UI (Alpine.js) ──(fetch GET/POST)──→ FastAPI (/api/file-manager/*) ──(validate paths)──→ Local Filesystem
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/pit_panel/web/routes/file_manager.py` | Create | Contains FastAPI routes for file CRUD, upload, and WebSocket terminal. |
| `src/pit_panel/web/templates/file_manager.html` | Create | Alpine.js-powered file manager dashboard interface. |
| `src/pit_panel/web/templates/system_terminal.html` | Create | Interactive web terminal interface with xterm.js setup. |
| `src/pit_panel/web/routes/__init__.py` | Modify | Import and export the new `file_manager` router. |
| `src/pit_panel/web/app.py` | Modify | Include the new `file_manager` router in FastAPI application setup. |
| `src/pit_panel/web/templates/base.html` | Modify | Add sidebar navigation links for Terminal and File Manager. |

---

## Interfaces / Contracts

### Frontend Web Terminal (HTML / xterm.js)
```html
<div class="h-96 flex flex-col bg-slate-950 rounded-lg overflow-hidden border border-slate-800">
    <div class="bg-slate-900 px-4 py-2 border-b border-slate-800 flex justify-between">
        <span class="text-xs font-mono text-slate-400">bash / powershell</span>
    </div>
    <div id="terminal-container" class="flex-grow p-4"></div>
</div>
<script>
    const term = new Terminal({ cursorBlink: true, fontFamily: 'JetBrains Mono, monospace' });
    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById('terminal-container'));
    fitAddon.fit();
    const ws = new WebSocket(`ws://${location.host}/system/terminal/ws`);
    term.onData(data => ws.send(data));
    ws.onmessage = event => term.write(event.data);
</script>
```

### File Manager UI Structure (Alpine.js)
```html
<div x-data="fileManager('/opt/pit-panel')" class="flex h-screen bg-slate-900 text-slate-100">
    <div class="w-64 border-r border-slate-800 p-4">Directories...</div>
    <div class="flex-1 flex flex-col">
        <div class="border-b border-slate-800 p-4 flex justify-between">
            <span x-text="currentPath"></span>
        </div>
        <div class="p-4 grid grid-cols-6 gap-4">
            <template x-for="item in items" :key="item.path">
                <div @click="open(item)" class="cursor-pointer p-2 border border-slate-800 hover:bg-slate-800">
                    <span x-text="item.name"></span>
                </div>
            </template>
        </div>
    </div>
</div>
```

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Path Traversal Guard | Assert `validate_safe_path` raises `PermissionError` when trying to escape with `..` or non-whitelisted paths. |
| Integration | CRUD operations | Test GET/POST API endpoints with mock data to create, read, update, and delete files inside `/opt/pit-panel`. |
| E2E | Web Terminal | Use Playwright to connect to `/system/terminal/ws`, send commands, and verify echo output in `xterm.js`. |

---

## Migration / Rollout

No database schema migrations or state upgrades are required. Access is gated by `get_admin` session cookies.

---

## Open Questions

- [ ] Should we support text editing in a custom CodeMirror/Monaco editor, or is a plain `<textarea>` sufficient for initial release?
- [ ] Should terminal resize events (`resize` payload) be handled over the WebSocket to adjust process columns/rows?

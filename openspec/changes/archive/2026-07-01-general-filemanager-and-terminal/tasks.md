# Tasks: Host Web Terminal and File Manager

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

## Phase 1: Foundation and Infrastructure

- [x] 1.1. Create safety path validation utilities using `pathlib.Path.resolve` and `Path.is_relative_to` in `src/pit_panel/web/routes/file_manager.py` or a shared helper to guard allowed directory roots (`/opt/pit-panel`, `/etc/pit-panel`, `/var/lib/pit-panel`).
- [x] 1.2. Update `src/pit_panel/web/routes/__init__.py` to import and export the upcoming `file_manager` router.
- [x] 1.3. Modify `src/pit_panel/web/app.py` to register the new `file_manager` router.

## Phase 2: Core Backend Implementation

- [x] 2.1. Implement file CRUD endpoints (list, read, write, create, upload, delete) in `src/pit_panel/web/routes/file_manager.py`, protected by existing admin session checks.
- [x] 2.2. Implement the WebSocket endpoint `/system/terminal/ws` in `src/pit_panel/web/routes/file_manager.py` using `asyncio.create_subprocess_exec` to spawn and manage a shell process (`powershell.exe` on Windows, `/bin/bash` or `sh` on Linux) with bidirectional I/O piped over the WebSocket.

## Phase 3: Frontend Implementation

- [x] 3.1. Create `src/pit_panel/web/templates/file_manager.html` utilizing Alpine.js for interactive directory navigation, file editing, and operations.
- [x] 3.2. Create `src/pit_panel/web/templates/system_terminal.html` utilizing xterm.js and the fit addon loaded from CDN.
- [x] 3.3. Modify `src/pit_panel/web/templates/base.html` to add sidebar navigation links for Terminal and File Manager.

## Phase 4: Testing and Verification

- [x] 4.1. Add unit tests verifying that path traversal attempts raise errors or get rejected by the safety validator.
- [x] 4.2. Write integration tests for all file manager CRUD endpoints.
- [x] 4.3. Implement tests for the WebSocket terminal connection to verify prompt execution and output feedback.

## Phase 5: Cleanup and Documentation

- [x] 5.1. Perform code style checking and linting using `uv run ruff check`.
- [x] 5.2. Run full test suite using `uv run pytest -q`.
- [x] 5.3. Update documentation with information regarding base directories and terminal environment settings.

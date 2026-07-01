# Tasks: Fix Proposals 1 to 4

## Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1 (Foundation/Infrastructure)
- [x] 1.1: Ensure `/usr/local/bin/uv` symlink points to Astral's installed `uv` binary in [install.sh](file:///C:/Users/pietr/progetti/pit-panel/packaging/install.sh).
- [x] 1.2: Add NOPASSWD rules in [install.sh](file:///C:/Users/pietr/progetti/pit-panel/packaging/install.sh) to `/etc/sudoers.d/pit-panel` for required git commands.
- [x] 1.3: Add NOPASSWD rules in [install.sh](file:///C:/Users/pietr/progetti/pit-panel/packaging/install.sh) to `/etc/sudoers.d/pit-panel` for uv commands.
- [x] 1.4: Add NOPASSWD rules in [install.sh](file:///C:/Users/pietr/progetti/pit-panel/packaging/install.sh) to `/etc/sudoers.d/pit-panel` for ufw deny and delete commands.

## Phase 2 (Core Implementation)
- [x] 2.1: Add optional `env` argument to `exec_command` in [docker_ops.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/docker_ops.py) to map variables into `-e` arguments.
- [x] 2.2: Refactor postgres backup process in [backup.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/backup.py) to pass PGPASSWORD via `env` without using shell wrap `sh -c`.
- [x] 2.3: Modify `_run_cmd` in [security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py) to pipe configured `sudo_password` (via `sudo -S` and stdin) when the command is `sudo`.
- [x] 2.4: Remove legacy raw ALTER TABLE query from `init_db` in [session.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/db/session.py).
- [x] 2.5: Standardize service restarts inside [pit-panel-updater.service](file:///C:/Users/pietr/progetti/pit-panel/packaging/pit-panel-updater.service) on the `--no-block` flag.

## Phase 3 (Testing/Verification)
- [x] 3.1: Add unit tests in [test_security_core.py](file:///C:/Users/pietr/progetti/pit-panel/tests/unit/test_security_core.py) to verify `_run_cmd` formats sudo inputs correctly when settings contain a password.
- [x] 3.2: Add unit tests in [test_docker_ops.py](file:///C:/Users/pietr/progetti/pit-panel/tests/unit/test_docker_ops.py) to verify env variables are properly processed by `exec_command`.
- [x] 3.3: Verify database initialization without manual queries passes integration tests.
- [x] 3.4: Execute `uv run pytest` and verify all tests pass, and run linter `uv run ruff check src/ tests/`.

## Phase 4 (Cleanup/Documentation)
- [x] 4.1: Perform code comments and formatting audit on all modified files.

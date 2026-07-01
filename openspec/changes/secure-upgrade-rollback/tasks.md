# Tasks: Secure Upgrade Rollback

## Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

---

## Phase 1: Foundation & Infrastructure (Path Resolution Helpers)
- **1.1. Implement git SHA lookup**
  - Add helper function `_get_current_sha()` using `git -C /opt/pit-panel rev-parse HEAD` to capture the pre-upgrade target.
- **1.2. Implement dynamic UV resolver**
  - Add helper function `_resolve_uv_bin()` using `shutil.which("uv")`.
  - Add prioritized fallback list: `/usr/local/bin/uv`, `/usr/bin/uv`, `/opt/pit-panel/.venv/bin/uv`, `/root/.cargo/bin/uv`.
- **1.3. Implement Python executable resolver**
  - Define `python_bin` referencing `sys.executable` to run within the active environment.

## Phase 2: Core Backend Implementation (Upgrade Route Refactoring)
- **2.1. Refactor `system_upgrade` post handler**
  - Retrieve the current SHA using `_get_current_sha()` and resolve the `uv` and `python` paths prior to starting upgrade steps.
- **2.2. Update upgrade sequence steps**
  - Configure the step list using dynamic `uv_bin` and `python_bin` paths.
  - Insert compilation check command: `[python_bin, "-m", "compileall", "-q", f"{INSTALL_DIR}/src"]` after `uv sync`.
- **2.3. Implement automatic rollback logic**
  - Wrap pipeline steps in a loop with failure detection.
  - On failure, execute rollback steps: git hard reset to original SHA, `uv sync`, and `systemctl daemon-reload`.
- **2.4. Refactor logging response**
  - Format logs to show `OK` / `FAIL` prefix and prepend `[ROLLBACK]` for rollback actions. Ensure the DB update history entry reflects the correct outcome.

## Phase 3: Testing & Verification
- **3.1. Verify UV path resolution logic**
  - Test `_resolve_uv_bin` behavior by mocking `shutil.which` outputs and asserting proper fallbacks.
- **3.2. Test compilation checks and rollback**
  - Mock `subprocess.run` to trigger exit code `1` during python compilation.
  - Assert that git reset executes with the original pre-upgrade SHA and verifying rollback logs appear.
- **3.3. Test normal upgrade execution**
  - Assert successful upgrade path logs `OK` and triggers daemon restart.
- **3.4. Test rollback failure handling**
  - Assert that the route handles rollback command errors gracefully without crashing the endpoint.

## Phase 4: Cleanup & Documentation
- **4.1. Run code check & quality gates**
  - Verify styling and imports via `uv run ruff check`.
  - Validate tests run successfully with `uv run pytest -q`.

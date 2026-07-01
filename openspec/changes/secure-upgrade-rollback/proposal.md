# Proposal: Secure Upgrade Rollback

## Intent

Implement a pre-flight syntax check and automatic rollback capability inside the `/system/upgrade` route to prevent service crashes due to broken pulled code.

## Scope

### In Scope
- Dynamically resolve `uv` and `python` paths to avoid hardcoded binary path mismatches.
- Add a Python compilation step (`python -m compileall`) right after `uv sync` during upgrade execution.
- Implement an automatic rollback block (`git reset --hard` to original HEAD SHA, `uv sync`, `systemctl daemon-reload`) if any upgrade step fails.
- Ensure the restart command uses the absolute path `/usr/bin/systemctl restart`.

### Out of Scope
- Reverting database migrations (handled separately).
- Reverting custom changes that are not committed.

## Capabilities

### New Capabilities
None

### Modified Capabilities
None

## Approach

1. Before execution, fetch the original git HEAD SHA to serve as the recovery target.
2. Resolve the `uv` and `python` executables dynamically using Python's `sys.executable` or environment lookups.
3. Add a compilation check step (`python -m compileall`) after updating code and syncing dependencies to ensure syntax validity.
4. Wrap upgrade steps in a try-except/conditional sequence. If any step fails, run rollback steps: hard reset to the original SHA, `uv sync`, and reload systemd config.
5. Use `/usr/bin/systemctl` for daemon reloading and restart trigger.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| [src/pit_panel/web/routes/system.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/system.py) | Modified | Implement dynamic resolution, compile step, and automatic rollback on failure in the upgrade post route. |
| [tests/unit/test_system.py](file:///C:/Users/pietr/progetti/pit-panel/tests/unit/test_system.py) | Modified | Assert the rollback behavior, new compile step, and verify dynamically resolved paths under test scenarios. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Rollback itself fails | Low | Keep rollback steps basic (git reset, uv sync, daemon-reload) using already-cached valid inputs. |

## Rollback Plan

If any step in the upgrade process fails, the system executes an automated Git reset back to the original HEAD SHA, followed by a local dependencies sync (`uv sync`) and systemctl daemon reload.

## Dependencies

None

## Success Criteria

- [ ] Successful upgrades proceed normally and restart the service.
- [ ] Any failure (e.g., compileall failing on invalid python syntax) automatically triggers a rollback to the initial state.
- [ ] No hardcoded binary paths are used for `python` or `uv`.

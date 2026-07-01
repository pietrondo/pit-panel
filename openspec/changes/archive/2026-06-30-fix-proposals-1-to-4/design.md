# Design: Fix Proposals 1 to 4

## Technical Approach

We will resolve critical security, database debt, and deployment integration issues.
1. **Shell Injection Prevention**: Eliminate `sh -c` inside PostgreSQL backup routines by using `docker compose exec -e` to securely inject the password environment variable.
2. **Sudoers Expansion**: Update `/etc/sudoers.d/pit-panel` to explicitly allow NOPASSWD execution for Git, UV, and UFW delete/deny commands.
3. **No-Block Alignment**: Standardize all service restarts inside the self-updater service on the `--no-block` flag.
4. **Sudo Password Fallback**: Modify the command execution handler inside the security module to optionally run `sudo -S` using the configured `sudo_password` secret if available.
5. **Database Initializer Clean Up**: Remove temporary database schema migration queries from the SQLAlchemy startup routing.

---

## Architecture Decisions

### Decision: Parameterized Environment Variable Injection for Backups
- **Choice**: Extend the `DockerManager.exec_command` API to support an optional `env` mapping, generating `-e KEY=VAL` options for `docker compose exec`.
- **Alternatives considered**: Writing PG credentials to a temporary file (rejected due to disk I/O risks).
- **Rationale**: Avoids `sh -c` shell wrapping, mitigating command/password injection.

### Decision: Least Privilege Sudoers Policies for Git & UV
- **Choice**: Specify narrow wildcard patterns in `/etc/sudoers.d/pit-panel` for required `git` and `uv` operations. Ensure a symlink `/usr/local/bin/uv` points to Astral's installed `uv` binary.
- **Alternatives considered**: General sudo access for `git` (rejected as insecure).
- **Rationale**: Restricts system execution strictly to self-updating directories.

### Decision: Centralized Sudo Password Handling
- **Choice**: Adapt `_run_cmd` in `security.py` to pipe the configured `sudo_password` (via `sudo -S` and stdin) when the command calls `sudo` and the password secret exists.
- **Alternatives considered**: Propagating `sudo_password` to all individual functions (rejected as bloated code).
- **Rationale**: Keeps security components simple and DRY.

### Decision: DB Startup Cleanup
- **Choice**: Remove the manual `ALTER TABLE` statement from the startup database engine block.
- **Alternatives considered**: Retaining the try-except query block (rejected as unnecessary debt).
- **Rationale**: `Base.metadata.create_all` automatically provisions `is_main_domain` on new installations; legacy databases have already executed this migration.

---

## Data Flow

```
[Backup Routine] ──(env: PGPASSWORD)──> [DockerManager] ──> [docker compose exec -e] ──> [pg_dump]
                                                                                            
[Security Router] ──(piped password)──> [security._run_cmd] ──(stdin: sudo -S)──────────> [ufw / fail2ban]
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/pit_panel/core/docker_ops.py` | Modify | Add optional `env` argument to `exec_command` routing. |
| `src/pit_panel/core/backup.py` | Modify | Update postgres dump invocation to use `env` dict and drop shell wrap. |
| `packaging/install.sh` | Modify | Add `git`, `uv`, and `ufw` deny/delete commands to `/etc/sudoers.d/pit-panel` configuration; ensure `/usr/local/bin/uv` symlink. |
| `packaging/pit-panel-updater.service` | Modify | Append `--no-block` to systemctl service restart commands. |
| `src/pit_panel/core/security.py` | Modify | Implement stdin password piping using `sudo_password` in `_run_cmd`. |
| `src/pit_panel/db/session.py` | Modify | Remove the legacy raw `ALTER TABLE` migration block from `init_db`. |

---

## Interfaces / Contracts

### `DockerManager.exec_command` signature update:
```python
async def exec_command(
    self,
    subdomain: str,
    service: str,
    cmd: list[str],
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
```

### `security._run_cmd` stdin logic:
```python
async def _run_cmd(cmd: list[str], timeout: int = 10, input: str | None = None) -> str:
    # If cmd[0] == "sudo" and Settings.sudo_password is set:
    # 1. Replace "sudo" + "-n" with "sudo" + "-S"
    # 2. Prepend "password\n" to input
```

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Backup postgres command formatting | Run test checking correct `exec_command` arguments and `env` extraction. |
| Unit | Security password redirection | Verify `_run_cmd` formats sudo inputs correctly when settings contain a password. |
| Integration | Database initialization | Check database schema creation without any manual queries. |

---

## Migration / Rollout

No migration required.

---

## Open Questions

None.

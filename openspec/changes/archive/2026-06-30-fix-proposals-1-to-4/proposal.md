# Proposal: Fix Proposals 1 to 4

## Intent
Resolve critical sudoers permission mismatches in updater/firewall, fix shell injection vulnerability in backups, clean up SQLAlchemy init_db schema migration debt, and update testing/documentation configurations.

## Scope

### In Scope
- Add git, uv, ufw deny/delete rules to sudoers templates/config.
- Update updater systemctl restart command to include --no-block in the updater service definition.
- Refactor security commands in core/security.py to accept and use sudo_password.
- Rewrite pg_dump execution in backup.py to pass PGPASSWORD via env dictionary and execute without sh -c.
- Remove raw ALTER TABLE query from init_db in session.py.

### Out of Scope
- Redesigning updater/firewall architecture.
- Migrating database tables not mentioned in the scope.

## Capabilities
### New Capabilities
None
### Modified Capabilities
None

## Approach
- Modify packaging/install.sh to include NOPASSWD access for required git, uv, and ufw subcommands.
- Update python subprocess calls inside packaging/pit-panel-updater.service to include `--no-block`.
- Implement environment variable passing for pg_dump in backup.py to avoid shell expansion.
- Clean up database initial migration duplication in session.py.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| src/pit_panel/core/backup.py | Modified | Remove sh -c, use env parameter |
| src/pit_panel/core/updater.py | Modified | Ensure updater processes use proper sudo permissions |
| src/pit_panel/core/security.py | Modified | Handle sudo_password in _run_cmd and align ufw commands |
| src/pit_panel/db/session.py | Modified | Remove raw ALTER TABLE query |
| packaging/install.sh | Modified | Add required sudoers permissions |
| packaging/pit-panel-updater.service | Modified | Add --no-block to systemctl restart |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Sudoers file syntax error | Low | Run visudo check if possible or test locally |

## Rollback Plan
Perform a git checkout/reset on modified files.

## Dependencies
None

## Success Criteria
- [ ] Subprocess backup executes pg_dump securely using env variables.
- [ ] Sudoers template has correct NOPASSWD permissions for git, uv, ufw.
- [ ] No raw ALTER TABLE runs on app start.

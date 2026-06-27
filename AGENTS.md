# pit-panel Agent Rules

## Stack
- Python 3.11+, FastAPI, Jinja2, HTMX 2, Alpine.js, Tailwind CSS
- SQLite + SQLAlchemy 2 async + Alembic
- systemd for service management
- Caddy for reverse proxy
- Docker Compose for app isolation

## Conventions
- Use `uv` for all Python operations
- Async SQLAlchemy throughout
- itsdangerous for session cookies
- TOML config at `/etc/pit-panel/config.toml`
- Data at `/var/lib/pit-panel/`
- Apps at `/opt/pit-panel/apps/<subdomain>/`

## Testing
- `uv run pytest` for all tests
- Integration tests use testcontainers
- E2E tests use Playwright
- **ALWAYS write/update tests when adding features** — minimum 1 test per new function/module
- Regression protection: if you fix a bug, write a test that reproduces it first
- **Run tests after every change**: `uv run pytest -q` before committing

## Critical Files
- **`packaging/install.sh`** — the Debian installer. If ANY bug is found during remote usage (curl pipe), fix this file immediately. Also run it locally after any change that affects startup, permissions, paths, or systemd units.
- **`packaging/pit-panel.service`** — systemd unit. Keep `Type=simple`. Ensure `ReadWritePaths` includes `.venv/` and `/var/lib/pit-panel`. **Never** use `StateDirectory=` or `ConfigurationDirectory=` with `ProtectSystem=strict` (they create empty private dirs that hide real files). Use `BindReadOnlyPaths=` for config files instead.

## Commit Rules
- **ALWAYS lint before committing**: `uv run ruff check src/ tests/` — fix ALL errors, never commit with lint
- **ALWAYS run tests before committing**: `uv run pytest -q` — 100% must pass
- Every commit MUST pass both commands — no exceptions

## Issue Tracking
- Use `bd` (beads) for ALL task tracking
- `bd ready --json` to find work
- `bd create "title" -d "desc" -t type -p priority --json`
- `bd close <id> --reason "done" --json`

## Server SSH

- `ssh pietro@192.3.187.125` — VPS di produzione
- `/opt/pit-panel/` — home app
- `sudo` richiede password (non passwordless)
- Usare `sudo -u pit-panel` per operazioni git lato server
- `git -C /opt/pit-panel fetch origin --prune` per pulire ref remoti

## Jules (Google AI Agent) Integration

Delega task autonomi a Jules tramite CLI. Ricaricare questa skill con `skill pit-panel-jules`.

### Setup
```bash
npm install -g @google/jules
jules login
```

### Comandi
| Comando | Descrizione |
|---------|-------------|
| `jules remote new --repo pietrondo/pit-panel --session "task"` | Crea sessione |
| `jules remote list --session` | Elenca sessioni |
| `jules remote pull --session <id>` | Recupera risultati |

### Task delegabili
- **Test**: `jules remote new --repo pietrondo/pit-panel --session "Add unit tests for src/..."`
- **Security**: `jules remote new --repo pietrondo/pit-panel --session "Security audit of src/... fix vulnerabilities"`
- **Refactoring**: `jules remote new --repo pietrondo/pit-panel --session "Extract X from file.py into new module"`
- **Bug fix**: `jules remote new --repo pietrondo/pit-panel --session "Write a test reproducing the bug, then fix it"`
- **Templates**: `jules remote new --repo pietrondo/pit-panel --session "Create Docker template for X in templates-app/"`

### Dopo il pull
```bash
jules remote pull --session <id>
uv run ruff check src/ tests/
uv run pytest -q
git add -A && git commit -m "jules: <desc>"
git push
```

### NON delegare a Jules
Decisioni architetturali (usa brainstorming), UI/UX redesign (usa impeccable), template Jinja2/HTML, migrazioni DB.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->

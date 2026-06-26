# pit-panel × Jules Skill

Delega task a **Jules** (Google's autonomous AI coding agent) via CLI per lavorare in parallelo su pit-panel.

## Prerequisiti

```bash
npm install -g @google/jules
jules login
```

Il repo deve essere connesso a Jules:
```bash
jules remote list --repo
```

## Comandi Jules

| Comando | Descrizione |
|---------|-------------|
| `jules remote new --repo pietrondo/pit-panel --session "task"` | Crea sessione |
| `jules remote list --session` | Elenca sessioni |
| `jules remote pull --session <id>` | Recupera risultati |
| `jules` | Dashboard TUI interattiva |

## Task delegabili a Jules

### 1. Test (unit + integrazione)
```bash
jules remote new --repo pietrondo/pit-panel --session "Add unit tests for src/pit_panel/core/caddy.py - test add_subdomain, remove_subdomain, list_subdomains. Use pytest-asyncio. Follow existing test patterns in tests/"
```

### 2. Security fixes (autonomous)
```bash
jules remote new --repo pietrondo/pit-panel --session "Security audit of src/pit_panel/web/routes/ - check for injection vulnerabilities, missing input validation, and CSRF protection. Fix any findings."
```

### 3. Refactoring (extract logic)
```bash
jules remote new --repo pietrondo/pit-panel --session "Refactor src/pit_panel/web/routes/security.py: extract the malware scan routes into a separate file src/pit_panel/web/routes/malware.py. Keep all imports and routes working."
```

### 4. Docker template creation
```bash
jules remote new --repo pietrondo/pit-panel --session "Create a new Docker app template in templates-app/ for Laravel. Create meta.json, docker-compose.yml.tpl, and env.tpl. Follow the pattern from templates-app/wordpress/"
```

### 5. Bug fix (repro first)
```bash
jules remote new --repo pietrondo/pit-panel --session "Write a test that reproduces this bug: when deploying an app with a port that's already in use, the error is silently caught. Then fix the bug so the error is shown to the user. Files: src/pit_panel/web/routes/apps.py"
```

## Workflow integrato

Usare questo skill quando:
- Servono test per codice nuovo/esistente
- C'è un security fix da fare
- Refactoring di file grandi in moduli più piccoli
- Creazione di nuovi template Docker
- Bug fix con test di regressione

**Non usare** per:
- Decisioni architetturali (usa brainstorming)
- UI/UX redesign (usa impeccable)
- Modifiche a template Jinja2/HTML (richiedono contesto visivo)
- Operazioni su DB o migrazioni

## Dopo il pull

1. `jules remote pull --session <id>` → applica le modifiche
2. `uv run ruff check src/ tests/` → lint
3. `uv run pytest -q` → test
4. Revisiona le modifiche con `git diff`
5. `git add -A && git commit -m "jules: <descrizione>"`

## Esempio completo

```bash
# 1. Delega a Jules
jules remote new --repo pietrondo/pit-panel \
  --session "Add input validation to all Form parameters in src/pit_panel/web/routes/subdomains.py. Validate subdomain name format, max length, prevent XSS."

# 2. Prendi l'ID sessione dall'output
# jules remote list --session

# 3. Recupera quando finito
jules remote pull --session SESSION_ID

# 4. Verifica
uv run ruff check src/ tests/ && uv run pytest -q
git diff --stat
```

## Maintenance

Source: https://jules.google/docs/cli/reference
Check for CLI updates: `npm update -g @google/jules`

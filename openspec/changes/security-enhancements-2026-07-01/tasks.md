# Tasks: VPS Security Enhancements

## Review Workload Forecast
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: ask-on-risk
400-line budget risk: High

Recommended PR Split:
- **PR 1: API Rate Limiting & Folder Exclusions**
  - Apply `slowapi` rate limits on sensitive endpoints: `/setup-2fa`, `/settings/update`, and `/api/file-manager/save`.
  - Add exclusion logic (`.git`, `.venv`, `node_modules`) to pattern-based malware scans.
  - Unit/integration tests for rate-limiting and directory exclusion.
- **PR 2: Fail2ban Config Overrides & Lynis Hardening Audits**
  - Implement Fail2ban jail config retrieval, config override writer, and client reloading logic.
  - Implement Lynis system audit trigger, execution parser, and local JSON caching.
  - Integrate Fail2ban configuration inputs and Lynis audits list/trigger in UI dashboards.
  - Tests for override parsing, validation, and Lynis audits.
- **PR 3: UFW Firewall Rules Management & Lockout Protection**
  - Implement SSH port parser and client IP extraction headers helper.
  - Implement UFW status parsing (`ufw status numbered`), rule addition, and rule deletion wrappers.
  - Enforce lockout prevention checks on enable/rule update. Protect active SSH/IP rules from deletion.
  - Create the UFW firewall rules listing, creation form, status toggles, and warning prompts in UI.
  - Unit and integration tests for lockout prevention and UFW control commands.
- **PR 4: ClamAV Daemon Container Scanner & Guards**
  - Set up background persistent docker container for ClamAV daemon socket stream scans.
  - Implement socket scanner engine and target directory traversal skipping exclusions.
  - Enforce system memory check safety guard (requiring >= 2.0 GB memory).
  - Create ClamAV daemon management widgets and memory warning labels.
  - Tests for ClamAV daemon startup, memory guard, and mock clamd socket communication.

---

## Phase 1: Foundation (config and helpers)
- [x] **1.1. Client IP Detection Helper**
  - Implement `_get_client_ip(request: Request)` in [src/pit_panel/core/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py) parsing headers in sequence: `X-Forwarded-For`, `X-Real-IP`, falling back to `request.client.host`.
- [x] **1.2. SSH Port Detection Helper**
  - Implement `_detect_ssh_port()` in [src/pit_panel/core/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py) to read SSH port config from `/etc/ssh/sshd_config` (or run `sudo cat /etc/ssh/sshd_config` on `PermissionError`), falling back to port `22`.
- [x] **1.3. UFW Status Parser**
  - Write regex parser in [src/pit_panel/core/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py) to map output of `ufw status numbered` to structured objects containing index, port, protocol, action, and source.
- [x] **1.4. Host Memory Checker**
  - Write a helper to read total system physical memory from `/proc/meminfo` or parse `free -m` output for resource safety checks.
- [x] **1.5. Lynis Dat File Parser**
  - Implement parser for `/var/log/lynis-report.dat` in [src/pit_panel/core/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py) extracting `hardening_index`, `warning[]`, and `suggestion[]`.

## Phase 2: Core implementation (security core features)
- [x] **2.1. UFW Rules Mutator & Lockout Protection**
  - Implement `_add_ufw_rule` and `_delete_ufw_rule` wrappers in [src/pit_panel/core/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py).
  - Enforce lockout prevention: automatically allow SSH port and current client IP whenever UFW is enabled or rules are updated.
  - Block deletion of UFW rules that match the current SSH port or client IP, returning a 400 Bad Request error.
- [x] **2.2. Fail2ban Configuration Writer**
  - Implement `_save_jail_config` writing `bantime`, `findtime`, and `maxretry` override values to `/etc/fail2ban/jail.d/pit-panel-overrides.local`.
  - Validate parameters to ensure they are positive integers.
  - Trigger `fail2ban-client reload` to hot-apply configuration settings.
- [x] **2.3. ClamAV Daemon Socket Client**
  - Implement `ClamAVDaemonScanner` in [src/pit_panel/security/malware_scanner.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/security/malware_scanner.py) communicating with the persistent daemon container `pit-panel-clamav` via localhost port 3310 socket.
  - Implement directory pruning in python traversal (`os.walk`), skipping `.git`, `.venv`, and `node_modules` folders.
  - Integrate total memory guard check, refusing to enable background scanner if RAM < 2.0 GB.
- [x] **2.4. Lynis Audit Controller**
  - Implement background `run_lynis_audit` in [src/pit_panel/core/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py) running `sudo lynis audit system --quick`.
  - Save parsed audit outputs to `/var/lib/pit-panel/lynis_last_report.json` on completion.
  - Implement auto-installation logic for `lynis` using `apt-get` if executable is missing from system path.

## Phase 3: Integration & Web Routes (FastAPI routes)
- [x] **3.1. Slowapi Rate Limiting Decoration**
  - Add `@limiter.limit("5/minute")` to setup 2FA endpoint in [src/pit_panel/web/routes/auth_routes.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/auth_routes.py).
  - Add `@limiter.limit("10/minute")` to settings update endpoint in [src/pit_panel/web/routes/settings.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/settings.py).
  - Add `@limiter.limit("20/minute")` to file save endpoint in [src/pit_panel/web/routes/file_manager.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/file_manager.py).
- [x] **3.2. UFW API Endpoints**
  - Expose GET rules listing, POST rule creation, POST rule deletion, POST firewall enable, and POST firewall disable endpoints in [src/pit_panel/web/routes/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/security.py).
- [x] **3.3. Fail2ban configuration Endpoints**
  - Expose jail details fetch and update configuration endpoints in [src/pit_panel/web/routes/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/security.py).
- [x] **3.4. ClamAV Daemon Manager Endpoint**
  - Expose control paths for background container state toggling and memory warning status.
- [x] **3.5. Lynis Audit Endpoints**
  - Expose background runner trigger and cached audit report reader in [src/pit_panel/web/routes/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/security.py).

## Phase 4: UI & Templates (Jinja2 templates)
- [x] **4.1. Firewall Rules Interface**
  - Design and integrate firewall grid UI inside [src/pit_panel/web/templates/security.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/security.html) featuring status widgets, rule addition forms, index deletes, and lockout alerts.
- [x] **4.2. Fail2ban Jails Tuner Interface**
  - Construct jail override configuration inputs inside [src/pit_panel/web/templates/security.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/security.html) validating entries.
- [x] **4.3. ClamAV Daemon Management Dashboard**
  - Render clamd container toggles, file traversal exclusion flags, and low memory warning cards.
- [x] **4.4. Lynis Audit Dashboard Visuals**
  - Render Lynis triggering indicators, score gauges, warning panels, and action suggestions list.

## Phase 5: Verification (pytest tests for each scenario)
- [x] **5.1. Parse Helpers Unit Tests**
  - Write test cases verifying correct parsing of `ufw status numbered`, `/etc/ssh/sshd_config` ports (and fallback cases), and `/var/log/lynis-report.dat`.
- [x] **5.2. Lockout Protection & Rules Mutators Tests**
  - Assert that client IP and SSH port are correctly extracted and whitelisted prior to firewall enable.
  - Verify rule deletions targeting active client IP or SSH ports are blocked.
- [x] **5.3. Fail2ban Overrides Validation Tests**
  - Verify integer parameter checks, writing of local config format overrides, and client reload calls.
- [x] **5.4. Socket Scanner & Pruning Tests**
  - Test `ClamAVDaemonScanner` using mock clamd responses over sockets.
  - Assert `.git`, `.venv`, and `node_modules` folders are skipped during scanning.
  - Verify memory check triggers correct warnings and limits container start options.
- [x] **5.5. Endpoint Rate Limiting Tests**
  - Generate multiple requests against 2FA, settings, and file save routes to confirm `429 Too Many Requests` is returned.
- [x] **5.6. Lynis Installer & Audit Flow Tests**
  - Mock audit command execution and check package installation fallback logic.
- [x] **5.7. Quality Gates Validation**
  - Execute `uv run ruff check src/ tests/` and `uv run pytest -q` to guarantee complete style compliance and code health.

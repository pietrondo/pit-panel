# Proposal: VPS Security Enhancements

## Intent

Enhance the panel's VPS security management features by implementing interactive UFW rule management with lockout prevention, Fail2ban jail-specific numerical parameters, ClamAV daemon performance optimization, and rate-limiting on sensitive endpoints.

## Scope

### In Scope
- **UFW Rule Management & Lockout Protection**: 
  - Expose UFW rule listing, custom rule creation (allow/deny by port, protocol, and source IP), and rule deletion.
  - Enforce strict lockout prevention by automatically detecting the active SSH port (parsed from SSH config or environment) and the user's active client IP (from the FastAPI connection request) and whitelisting them before rules are applied or UFW is enabled.
- **Fail2ban Jail Customization**:
  - Expose numerical configuration inputs in the UI and endpoints to set `bantime`, `findtime`, and `maxretry` on a per-jail basis.
  - Dynamically write these settings into local Fail2ban configuration overrides (e.g. `/etc/fail2ban/jail.d/` or `/etc/fail2ban/jail.local`) and trigger a reload.
- **Malware Scanner (ClamAV Daemon)**:
  - Migrate from launching an ephemeral Docker container for each malware scan (which reloads the database and takes 30-90s) to a persistent background `clamav/clamav:latest` daemon container running `clamd`.
  - Interact with `clamd` via unix or TCP socket (port 3310).
- **Target Folder Exclusions**:
  - Add exclusion lists (`.git`, `.venv`, `node_modules`) to both the pattern scanner and ClamAV scanner to skip massive search spaces and speed up scans.
- **API Hardening (Rate Limiting)**:
  - Decorate sensitive endpoints with `slowapi` rate limits:
    - 2FA setup (`POST /setup-2fa` in `auth_routes.py`)
    - Settings updates (`POST /settings/update` in `settings.py`)
    - File manager saves (`POST /api/file-manager/save` in `file_manager.py`)
- **System Hardening Audits (Lynis Integration)**:
  - Integrate **Lynis** (security auditing tool for Unix-like systems) to perform automated security scans.
  - Expose UI action to trigger an audit (`lynis audit system --quick` via sudo).
  - Parse the Lynis report data (located at `/var/log/lynis-report.dat`) to extract key metrics (Hardening Index, Warnings, Suggestions, scan timestamp).
  - Render the audit results in a dedicated UI dashboard tab, highlighting warnings and recommendations.

### Out of Scope
- **2FA Global Enforcement**: Do NOT implement global redirect enforcement for users without 2FA enabled for now (low priority/omitted).
- **Intrusion Detection System (IDS)**: Setting up OSSEC/Wazuh or deep packet inspection.

## Capabilities

### New Capabilities
- Fine-grained UFW firewall rule addition and deletion.
- Individual Fail2ban jail configuration tuning (`bantime`, `findtime`, `maxretry`).
- Background persistent ClamAV service execution.
- Automated system hardening audit triggering and parsed report visualization (Lynis).

### Modified Capabilities
- High-performance malware scans (reduced from minutes to seconds).
- Abuse protection on sensitive admin routes.

## Approach

1. **Lockout Protection & UFW**:
   - Write a helper to resolve the server's configured SSH port (defaulting to 22, but parsing `/etc/ssh/sshd_config` if present) and get the client's IP from the request state (`request.client.host`).
   - Implement rule creation/deletion wrappers in `src/pit_panel/core/security.py`. When enabling UFW or applying custom rules, explicitly insert `allow` rules for the detected SSH port and active IP.
2. **Fail2ban Jails Config**:
   - Create a module helper to update `/etc/fail2ban/jail.local` or individual jail config files in `/etc/fail2ban/jail.d/` using Python's `configparser` or a template.
   - Provide routes to get and set jail configuration values, restarting/reloading fail2ban after updates.
3. **ClamAV daemon**:
   - Manage a persistent `clamav-daemon` docker container using `docker_ops.py` or shell commands.
   - Use Python's built-in socket programming or `aioclamd` to connect to port 3310 on localhost or the container's network and run a socket stream scan.
4. **Scanner Exclusions**:
   - Exclude `.git`, `.venv`, and `node_modules` from directory traversal in `scan_patterns`.
   - Configure ClamAV scan options to exclude these directories.
5. **Slowapi Rate Limits**:
   - Apply `@limiter.limit` to `setup_2fa_post` (e.g. `5/minute`), `settings_update` (e.g. `10/minute`), and `save_file` (e.g. `20/minute`).
6. **Lynis Security Audits**:
   - Add Lynis installation check and execute `lynis audit system --quick` inside `src/pit_panel/core/security.py` using `asyncio.create_subprocess_exec` under sudo.
   - Write a custom python parser to read `/var/log/lynis-report.dat`, extracting variables such as `hardening_index`, `warning[]`, and `suggestion[]`.
   - Store the parsed output as a JSON blob or cache file `/var/lib/pit-panel/lynis_last_report.json` for fast display.
   - Expose endpoints `POST /security/audit/run` and `GET /security/audit/report` in `security.py` routes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| [src/pit_panel/core/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/core/security.py) | Modified | Implement UFW rule addition/deletion, SSH port/client IP detection. Implement Fail2ban jail parameter updates. Implement Lynis execution and report parser. |
| [src/pit_panel/security/malware_scanner.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/security/malware_scanner.py) | Modified | Update ClamAV scanner to query a persistent `clamd` container via socket. Implement `.git`, `.venv`, `node_modules` exclusions. |
| [src/pit_panel/web/routes/security.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/security.py) | Modified | Add routes for custom UFW rules, Fail2ban parameters configuration, ClamAV daemon control, and Lynis audits. |
| [src/pit_panel/web/routes/settings.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/settings.py) | Modified | Add rate limiting to `/settings/update` post endpoint. |
| [src/pit_panel/web/routes/auth_routes.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/auth_routes.py) | Modified | Add rate limiting to `/setup-2fa` post endpoint. |
| [src/pit_panel/web/routes/file_manager.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/file_manager.py) | Modified | Add rate limiting to `/api/file-manager/save` endpoint. |
| [src/pit_panel/web/templates/security.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/security.html) | Modified | Add tab elements, dialogs, and tables to view/edit UFW rules, configure Fail2ban jails, manage ClamAV daemon, and trigger/visualize Lynis audits. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Admin Lockout via UFW | Medium | Automatically inject allow rules for current SSH port and browser client IP address on rule updates. Warn users if deleting rules matching these settings. |
| Memory Exhaustion from ClamAV | High | `clamd` uses ~1-1.5GB RAM. We will check available system memory before enabling/recommending ClamAV. Low-resource systems (<2GB RAM) will display a warning and fall back to pattern-based scans. |
| Fail2ban restart downtime | Low | Perform quick reloads rather than full restarts where possible to maintain ssh monitoring. |
| Lynis missing command | Low | Ensure the panel falls back gracefully or tries to auto-install `lynis` using apt if missing. |

## Rollback Plan

If firewall or fail2ban configuration errors occur:
- Revert `/etc/fail2ban/jail.local` or overrides to the previous configuration backup.
- Disable UFW if a lockout condition is suspected (`ufw disable`).
- Stop the ClamAV persistent docker container.
- Clean up any generated Lynis audit temp logs if needed.

## Dependencies

- Docker installed and active on target system (already exists).
- `slowapi` library (already integrated).
- `lynis` CLI package on Debian (will be checked/installed if possible).

## Success Criteria

- [ ] Custom UFW rules can be successfully created and deleted via the web UI.
- [ ] Active sessions (SSH and web panel) are never locked out when updating firewall configurations.
- [ ] Fail2ban parameters (`bantime`, `findtime`, `maxretry`) are numerically configurable per-jail and applied.
- [ ] ClamAV scans run via a persistent `clamd` service, completing within seconds instead of loading databases from scratch.
- [ ] Large directories (`.venv`, `.git`, `node_modules`) are skipped in both pattern and ClamAV malware scans.
- [ ] Sensitive endpoints `/setup-2fa`, `/settings/update`, and `/api/file-manager/save` are rate-limited.
- [ ] Lynis audits can be run from the UI and show a parsed score, warnings, and suggestions correctly.
- [ ] No global redirect enforcement for 2FA is added.

# Exploration: VPS Security Enhancements in Pit-Panel

This document explores options and security improvements for VPS security features (firewall management, fail2ban configuration, malware scan optimizations, rate limiting, audit logging, and 2FA settings) in the `/security` area of the panel.

## Current State

### 1. Firewall Management (UFW)
- **Status Check**: The backend queries `ufw status numbered` and parses output. It automatically installs and enables `ufw` if missing or inactive, opening ports `22`, `80`, `443`, and `8080`.
- **IP Blocking**: Denying an IP runs `ufw deny from <ip>` and records it in the DB. Unbanning deletes that deny rule.
- **Missing Controls**: No UI/API exists for adding custom firewall rules (ports, protocols, profiles), deleting individual rules, or setting/viewing default incoming/outgoing policies.

### 2. Fail2Ban Config
- **Status Check**: The backend runs `fail2ban-client status`. If not found, it installs `fail2ban`, writes a default `jail.local` configuration, and restarts the service.
- **Jail Management**: The UI shows active jails and allows enabling default jails (`sshd`, `sshd-ddos`, `nginx-http-auth`, `apache-auth`, `postfix`).
- **IP Unbanning**: Allows unbanning IPs from specific jails via `fail2ban-client set <jail> unbanip <ip>`.
- **Missing Controls**: No UI/API is available to view jail-specific stats, edit global ban parameters (`bantime`, `findtime`, `maxretry`), or edit jail settings.

### 3. Malware Scan Optimizations
- **Engines**: Uses pattern scanning (regex/string checks for PHP/JS shell patterns) and ClamAV.
- **ClamAV Engine**: Starts a *new* docker container `clamav/clamav:latest` for *every* scan execution.
- **Performance Bottleneck**: Starting a ClamAV container each time requires loading the signature database (hundreds of MBs) from disk into RAM, taking 30-90 seconds per run, causing extreme CPU/memory spikes and timeouts.
- **Exclusion Directories**: The pattern scanner does not exclude large dependency folders like `node_modules/`, `.venv/`, `.git/`, leading to unnecessarily slow scans and potential false positives.

### 4. Rate Limiting
- **Implementation**: Utilizes `slowapi` with a default `get_remote_address` key function.
- **Application**: Only applied to the login POST route (`/login` with `5/minute`).
- **Missing Features**: High-risk routes (TOTP setup, password resets, file manager actions, system settings) lack rate limits. No admin-configurable limits exist in the UI.

### 5. Audit Logging
- **Implementation**: The backend captures actions on subdomains and backups in the `AuditLog` table.
- **UI/Management**: Recent entries are displayed as a flat list in the settings view, with a full list under `/settings/audit` limited to 100 entries.
- **Missing Features**: No searching, filtering (by user, action, target, IP), exporting (CSV/JSON), or pruning/retention policy configuration.

### 6. 2FA Settings
- **Implementation**: Users can configure 2FA via `/setup-2fa` (saves `totp_secret` and sets `totp_enabled` to True in DB).
- **Missing Features**: Superadmins cannot view other users' 2FA status, force 2FA globally for all panel users, or reset/disable 2FA for a locked-out user.

---

## Affected Areas

1. **`src/pit_panel/core/security.py`**
   - Extend UFW command execution wrappers to support rule addition, deletion, and policy status updates.
   - Extend Fail2ban configuration management to rewrite `jail.local` values dynamically.
2. **`src/pit_panel/security/malware_scanner.py`**
   - Redesign ClamAV scanning to interface with a running daemon (`clamd`) container over TCP or UNIX socket.
   - Introduce target folder exclusions (e.g. `node_modules`, `.venv`, `.git`) in `scan_patterns`.
3. **`src/pit_panel/web/routes/security.py`**
   - Add routes for UFW rule management (create, delete, toggle default policies).
   - Add routes to configure Fail2ban parameters and individual jails.
   - Add configuration parameters for global/custom rate limits.
   - Hook up global 2FA management controls (reset 2FA, enforce 2FA).
4. **`src/pit_panel/web/templates/security.html`**
   - Implement detailed UI tabs/cards for:
     - UFW detailed management (rules table, add rule dialog, default policy selector).
     - Fail2ban parameters form.
     - Rate limit thresholds config.
     - User 2FA status management (enable/disable enforcement, reset individual 2FA secrets).
5. **`src/pit_panel/web/routes/settings.py` & `src/pit_panel/web/templates/audit.html`**
   - Add search and filtering capabilities (by action, user, date range) to the audit log view.
   - Add an export CSV/JSON endpoint.
6. **`src/pit_panel/web/limiter.py` & `src/pit_panel/web/routes/auth_routes.py`**
   - Add rate limiting decorators to other sensitive routes (e.g., `/setup-2fa`).

---

## Approaches

### Approach 1: Monolithic Extension (Quick Fix)
Keep configuration inline in existing modules, adding simple endpoints for UFW rules and Fail2ban configs. For ClamAV, keep the CLI container run, but pass basic size limits and direct regex exclusions to the pattern scanner.
* **Pros**: Simple to write; minimal architectural changes; keeps the current code pattern.
* **Cons**: ClamAV scan performance remains poor (minutes per run, heavy resource consumption); rate limiting and 2FA settings are local and cannot be configured per user/endpoint.

### Approach 2: Modular Security Enhancements (Recommended)
Refactor firewall and fail2ban commands into robust helper modules. Keep a background ClamAV container running the `clamd` daemon to speed up scans by 10x-100x via socket communication. Implement directory exclusions. Expose dynamic rate limiting via database settings, and add a comprehensive Admin 2FA dashboard to reset and enforce 2FA.
* **Pros**: Significant performance boost for malware scans; high visual polish; fine-grained firewall and fail2ban controls; secure global 2FA enforcement; clean architectural separation.
* **Cons**: Higher initial implementation complexity; requires maintaining a persistent background container for clamd (approx. 200MB RAM footprint).

### Approach 3: Semi-Automated Hardening Script (CLI focused)
Use a background script/cron to harden UFW, fail2ban, and run ClamAV, only exposing high-level status toggles in the web interface.
* **Pros**: Offloads panel web CPU/resource footprint; easier to package as systemd services.
* **Cons**: Poor UX; user cannot see detailed UFW rules or customize ports easily; hard to interact with in real-time.

---

## Recommendation

We recommend **Approach 2 (Modular Security Enhancements)**.
- **Firewall**: Exposing standard port whitelist rules, block/allow rules, default policies, and rule deletion is essential for standard VPS administration.
- **Fail2ban**: Exposing maxretries and bantime settings allows admins to tailor blocking sensitivity without needing SSH access.
- **Malware Scanner**: Switching from CLI-based ephemeral containers to a persistent `clamd` service reduces scan time from minutes to seconds because ClamAV database signatures are pre-loaded in memory. Ignoring large package directories prevents false positives and system freeze.
- **2FA Management**: Critical for teams or multiple admins to prevent lockouts.

---

## Risks

1. **UFW Lockout**: Adding UFW rule management exposes the risk of an admin blocking port 22/80/443 or their own IP, locking them out of the VPS.
   - *Mitigation*: The backend should ensure SSH/panel ports are automatically allowed when UFW is enabled or default policy is modified. Add warning flags or an "auto-allow active session IP" logic.
2. **ClamAV Memory Usage**: A persistent `clamd` daemon requires a baseline of ~1-1.5GB of RAM to hold malware definitions. On low-memory VPS instances (e.g., 1GB RAM), this can crash the server.
   - *Mitigation*: Allow the user to choose between "Daemon scan" (requires >2GB RAM) and "Pattern scan" (lightweight PHP/JS scanning, negligible RAM). Disable ClamAV by default on low-memory boxes.
3. **Fail2ban Service Restart**: Applying changes to jail configurations requires a fail2ban restart, which could temporarily interrupt login monitoring.

---

## Ready for Proposal
Yes

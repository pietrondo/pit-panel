# VPS Security Enhancements Specification

## Purpose

Enhance VPS security management by implementing UFW firewall rules administration with lockout prevention, Fail2ban jail configuration tuning, low-overhead ClamAV persistent daemon scans with folder exclusions, API rate-limiting on sensitive operations, and system hardening audits using Lynis.

## Requirements

### Requirement: UFW Firewall Rules Management & Lockout Protection

The system MUST allow administrators to list UFW rules, create custom allow/deny rules (specifying port, protocol, and optionally source IP), and delete rules. To prevent administrative lockout, the system MUST enforce automatic whitelisting of the current SSH port and the active browser client IP before enabling the firewall or applying rules.

#### Scenario: List UFW Rules
- GIVEN an authorized administrator accessing the security dashboard
- WHEN the system queries UFW state
- THEN the system MUST return a structured list of firewall rules containing rule index, action (allow/deny), protocol (TCP/UDP/Any), port/port-range, source, and destination.

#### Scenario: Create Custom UFW Rule
- GIVEN an administrator providing a valid port or port-range, protocol, action, and source IP constraint
- WHEN the administrator submits the creation request
- THEN the system MUST validate the inputs and execute the rule creation via UFW
- AND the system MUST reload UFW to apply the rule.

#### Scenario: Lockout Prevention on Enable or Update
- GIVEN UFW is disabled, or a set of rules is being modified/reloaded
- WHEN the system processes the UFW enable or update command
- THEN the system MUST parse the configured SSH port from `/etc/ssh/sshd_config` (falling back to port 22 if unreadable or unspecified)
- AND the system MUST detect the active client IP address from the incoming FastAPI request
- AND the system MUST automatically insert UFW rules to allow traffic on the detected SSH port and from the detected client IP address BEFORE activating the firewall.

#### Scenario: Prevent Deletion of Active Access Rules
- GIVEN an administrator attempting to delete a rule that allows SSH port traffic or allows traffic from the current client IP address
- WHEN the deletion is requested
- THEN the system MUST either block the deletion or immediately re-inject the active connection bypass rule, returning a warning notification to the user to prevent accidental lockout.

---

### Requirement: Fail2ban Jail Customization

The system MUST expose configurable numeric parameters (`bantime`, `findtime`, `maxretry`) per Fail2ban jail, save these configurations to local jail overrides, and trigger a configuration reload.

#### Scenario: Update Fail2ban Jail Settings
- GIVEN an administrator updating numerical settings (`bantime`, `findtime`, `maxretry`) for a specific jail
- WHEN the system receives positive integer values for these parameters
- THEN the system MUST write these override parameters into a local Fail2ban configuration override file (e.g. `/etc/fail2ban/jail.d/pit-panel-overrides.conf` or equivalent)
- AND the system MUST execute a Fail2ban reload command (e.g., `fail2ban-client reload`) to apply changes without restarting the full service.

#### Scenario: Validation of Jail Input Values
- GIVEN an administrator entering a non-numeric, negative, or blank value for `bantime`, `findtime`, or `maxretry`
- WHEN the update request is processed
- THEN the system MUST reject the request with a 400 Bad Request error
- AND the system MUST NOT write changes to the disk or reload Fail2ban.

---

### Requirement: ClamAV Daemon Malware Scans & Folder Exclusions

The system MUST replace ephemeral ClamAV Docker scans with a persistent background daemon (`clamd` container) querying, support folder exclusions to optimize traversal speed, and implement system resource guards before recommending the daemon.

#### Scenario: Persistent ClamAV Socket Scan
- GIVEN the persistent ClamAV daemon container is active
- WHEN a malware scan is requested
- THEN the system MUST scan files by sending scan instructions to the `clamd` daemon via socket connection (Unix socket or TCP socket on port 3310)
- AND the system MUST NOT spin up a new container instance for the scan.

#### Scenario: Folders Exclusion List
- GIVEN a scan is initiated on a directory containing `.git`, `.venv`, or `node_modules` folders
- WHEN the scanner traverses the file tree
- THEN the scanner MUST exclude these directory names from the search space for both custom pattern matching and ClamAV socket streams.

#### Scenario: Low System Memory Protection
- GIVEN a host system with less than 2.0 GB of total or available physical memory
- WHEN the administrator attempts to enable the ClamAV persistent daemon
- THEN the system MUST display a warning notification regarding potential high memory usage and system instability
- AND the system SHOULD recommend pattern-based light scans as a fallback.

---

### Requirement: API Rate Limiting

The system MUST protect sensitive endpoints against abuse and brute-force attempts by enforcing rate limits via `slowapi`.

#### Scenario: Exceeding Route Limits
- GIVEN the following endpoints and their maximum request thresholds:
  - `POST /setup-2fa`: limit of 5 requests per minute
  - `POST /settings/update`: limit of 10 requests per minute
  - `POST /api/file-manager/save`: limit of 20 requests per minute
- WHEN a client exceeds these limits within the one-minute window
- THEN the system MUST return a 429 Too Many Requests HTTP status code.

---

### Requirement: System Hardening Audits (Lynis Integration)

The system MUST support triggering automated security audits using Lynis, parsing the audit report, caching results to a JSON file, and displaying the results on a dedicated dashboard tab.

#### Scenario: Run and Cache Lynis Audit
- GIVEN an administrator triggering a new Lynis audit from the UI
- WHEN the system executes `lynis audit system --quick` using elevated permissions (`sudo`)
- THEN the system MUST parse `/var/log/lynis-report.dat` to extract the hardening index, warnings, suggestions, and the timestamp
- AND the system MUST save the parsed results to `/var/lib/pit-panel/lynis_last_report.json` as a JSON cache.

#### Scenario: Display Cached Lynis Report
- GIVEN a request to view security audit results
- WHEN the system reads the cached audit file `/var/lib/pit-panel/lynis_last_report.json`
- THEN the system MUST return the hardening index, warning messages, suggestions list, and audit timestamp for UI rendering.

#### Scenario: Handle Missing Lynis Dependency
- GIVEN a system where the `lynis` binary is not found in the executable PATH
- WHEN a Lynis audit is requested
- THEN the system SHOULD attempt to auto-install `lynis` using the system package manager (e.g. `apt-get install lynis -y`)
- AND if installation fails, the system MUST return a warning message advising the administrator to install `lynis` manually.

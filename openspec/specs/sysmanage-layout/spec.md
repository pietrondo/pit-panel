# Specification: SysManage Layout

This specification defines the system management layout interface, organizing service controls, updates, system resources, logs, and power operations.

## 1. Overview
The Debian System Management (`SysManage`) dashboard offers controls for system-level services, system packages updates, resource usage charts/tables, logs auditing, and remote restart capabilities. This dashboard must be structured cleanly with tabbed navigation and secure confirm-before-run user controls.

## 2. Requirements

### 2.1 Tabbed Navigation Structure
- The `SysManage` dashboard MUST organize content into four main tabs:
  1. **Services**: Interactive service grids to start/stop/restart key host daemons (e.g., Caddy, Docker, SSHD).
  2. **Updates**: Package repository updates and upgrades.
  3. **Resources**: Real-time or snapshot metrics of CPU, RAM, and Disk space.
  4. **Logs**: Historical or stream logs from systemd journal.
- Switching tabs MUST NOT cause a full page refresh; it MUST use Alpine.js or HTMX dynamic swapping.

### 2.2 Sudo Action Protection and Feedback
- System actions running as `sudo` (e.g., restarting services, fetching updates) MUST include visual progress feedback.
- During execution, the trigger buttons MUST be disabled, and an HTMX loading indicator (`hx-indicator`) MUST display active progress to prevent multiple concurrent requests.
- Log outputs from these actions MUST be directed into the styled terminal emulator component.

### 2.3 Double-Confirmed Reboot Action
- The "Reboot Server" action MUST require two distinct user confirmation steps prior to executing the backend system reboot API.
- The UI MUST NOT expose a single-click reboot trigger.
- The reboot button MUST initially show an unlock or "Are you sure?" confirmation state, requiring a second click or checking a confirmation checkbox before firing the final API payload.

## 3. Scenarios

### Scenario 1: Switching SysManage Tabs
**GIVEN** the user is on the System Management (`/system/manage`) page
**WHEN** the user clicks on the "Logs" tab
**THEN** the logs panel MUST be displayed
**AND** the page MUST NOT perform a browser reload
**AND** the "Logs" tab header MUST be styled as the active tab.

### Scenario 2: Service Restart with Action Prevention
**GIVEN** the Caddy service is currently running
**WHEN** the user clicks the "Restart Caddy" button
**THEN** the button MUST be disabled
**AND** a loading spinner MUST appear on or beside the button
**AND** once complete, the output details MUST render in the styled terminal window.

### Scenario 3: Reboot Double Confirmation
**GIVEN** the user wishes to restart the server hosting pit-panel
**WHEN** the user clicks the initial "Reboot Server" button
**THEN** the UI MUST display a confirmation state (e.g. toggle to "Confirm Reboot" button or display a verification popup)
**AND** the final reboot request MUST NOT be sent to the server until the second validation/button click is performed.

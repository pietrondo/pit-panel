# Exploration: UI Restyling and SysManage Integration

This document outlines the findings, design opportunities, and implementation plan for restyling the user interface and fully integrating the Debian System Management (SysManage) page into the overall navigation and design system.

---

## 1. Core Codebase Analysis

We investigated the following core templates and routes:
- **Templates**: [base.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/base.html), [apps.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/apps.html), [app_detail.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/app_detail.html), [system_manage.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/system_manage.html), [security.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/security.html)
- **Routes**: [apps.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/apps.py), [system_manage.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/system_manage.py), [dashboard.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/dashboard.py)

### Findings:
1. **Layout & Sidebar State**: The sidebar has no JavaScript path detection. The `.sidebar-link.active` styles (indigo backgrounds/text) exist in the CSS block, but they are never applied to active items during navigation.
2. **Typography**: The application currently uses standard default browser sans-serif fonts without loading custom typography.
3. **App Listing**: The `/apps` list displays subdomains with their deployment stack, but does not provide real-time container states (e.g. running containers vs total containers) in the list view; users must click through to `/apps/{id}` to see actual status.
4. **SysManage Tabs**: The `system_manage.html` page uses Alpine.js tabs, but lacks visual cohesion with other panels and displays raw shell command output in a plain `<pre>` element.

---

## 2. Proposed UI/UX Upgrades

### A. Modern Typography & Aesthetics
- **Fonts**: Integrate Google Fonts (`Inter` for body copy, `Outfit` or `Plus Jakarta Sans` for headers, and `JetBrains Mono` or `Fira Code` for monospace terminal outputs) in [base.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/base.html).
- **Glassmorphism & Gradients**: 
  - Add gradient header overlays, glowing button accents, and unified card components.
  - Introduce custom transition animations and hover scales (`transform hover:-translate-y-0.5 hover:shadow-lg transition-all duration-300`).
- **Sidebar Active Highlighting**: Add an inline layout initialization script in `base.html` to automatically tag sidebar items matching the current `window.location.pathname` with the `.active` class:
  ```javascript
  document.addEventListener('DOMContentLoaded', () => {
      const currentPath = window.location.pathname;
      document.querySelectorAll('.sidebar-link').forEach(link => {
          const path = link.getAttribute('data-path');
          if (path === currentPath || (path !== '/' && currentPath.startsWith(path))) {
              link.classList.add('active');
          }
      });
  });
  ```

### B. Functional Enhancements for `/apps`
- **Dynamic Status Columns**: In the `/apps` table, display running/total container counts and active state badges. Update the `apps_list` route in [apps.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/apps.py) to retrieve container stats asynchronously.
- **Improved Stack Cards**: Restyle the "Choose a Stack" tiles with clean micro-animations, stack logo/icon headers, border glowing transitions, and subtle badge configurations.
- **Deploy Feedback UI**: Provide a visual stepper or progress indicator when a deployment is triggered using HTMX indicators.

### C. Integrating & Restyling `SysManage`
- **Navigation Cohesion**: Ensure `/system/manage` is highlighted as active in the sidebar.
- **Terminal Terminal UI Emulator**:
  - Restyle the `<pre id="result">` output container as a mock terminal window.
  - Include window control buttons (Red/Yellow/Green dots in a top bar), rounded corners, padding, custom dark scrollbars, and neon green/amber text color on a deep slate background.
- **Service Action Grids**: Redesign service action trigger buttons with real-time feedback spinners and success/error status lights.

---

## 3. Risks & Mitigations

- **Sudo Command Latency**: Actions in SysManage run via sudo and can take several seconds (especially `apt-get update`).
  - *Mitigation*: Ensure HTMX indicators (`hx-indicator`) are fully utilized with disabled states during execution to prevent double clicks and communicate loading states.
- **Alpine.js Conflicts**: Multiple inline scripts define `alpine:init`.
  - *Mitigation*: Consolidate all global layouts and layout helpers into a single central Alpine script initialization in `base.html`.
- **CSS Cache Evasion**: Tailwind CSS is loaded from a CDN. Custom themes must be declared in the inline `tailwind.config` block.
  - *Mitigation*: Document all extended Tailwind config colors and theme utilities clearly in the setup rules.

---

## 4. Next Recommended Phase

1. **Design Proposal (`sdd-propose`/`sdd-spec`)**: Draft exact UI wireframes, tailwind theme configs, and HTML snippets.
2. **Implementation Tasks (`sdd-tasks`)**: Divide changes into manageable backend and frontend tasks.

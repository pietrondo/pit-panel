# Specification: Sidebar Active Detection

This specification defines the behavior for automatically highlighting active navigation sidebar links based on the current browser URL path.

## 1. Overview
The sidebar navigation links must dynamically receive an active style to indicate to the user which section of the application is currently active. This is to be implemented with lightweight, client-side JavaScript that executes on page load, minimizing template rendering logic.

## 2. Requirements

### 2.1 Navigation Markup and Attributes
- Each navigation link element (`.sidebar-link`) MUST contain a `data-path` attribute containing the relative target URL path (e.g., `/`, `/apps`, `/system/manage`).
- The base stylesheet MUST define an `.active` selector (or utility class equivalent, such as Tailwind classes) representing the active visual state.

### 2.2 Active Link Detection Logic
- The system MUST query all sidebar link elements on DOM content load.
- The system MUST retrieve the current URL's pathname via `window.location.pathname`.
- For each link:
  - If the link's `data-path` is `/` (root), it MUST be marked active ONLY when `window.location.pathname` is exactly `/`.
  - If the link's `data-path` is NOT `/`, it MUST be marked active if `window.location.pathname` is exactly equal to the `data-path`, OR if `window.location.pathname` starts with the `data-path` followed by a slash (e.g., `/apps` matches `/apps` and `/apps/123`).
- When a link is determined to be active, the system MUST add the `.active` class to the link element.
- All non-matching links MUST NOT have the `.active` class applied.

## 3. Scenarios

### Scenario 1: Exact Match on Root Path
**GIVEN** the user is viewing the root dashboard page (`/`)
**AND** the sidebar contains a link with `data-path="/"` and another link with `data-path="/apps"`
**WHEN** the DOM content is fully loaded
**THEN** the link with `data-path="/"` MUST have the `active` class
**AND** the link with `data-path="/apps"` MUST NOT have the `active` class

### Scenario 2: Exact Match on Sub-path
**GIVEN** the user is viewing the applications page (`/apps`)
**AND** the sidebar contains links with `data-path="/"`, `data-path="/apps"`, and `data-path="/system/manage"`
**WHEN** the DOM content is fully loaded
**THEN** the link with `data-path="/apps"` MUST have the `active` class
**AND** the link with `data-path="/"` MUST NOT have the `active` class
**AND** the link with `data-path="/system/manage"` MUST NOT have the `active` class

### Scenario 3: Nested Path Prefix Match
**GIVEN** the user is viewing an application detail page (`/apps/my-app-subdomain`)
**AND** the sidebar contains a link with `data-path="/apps"`
**WHEN** the DOM content is fully loaded
**THEN** the link with `data-path="/apps"` MUST have the `active` class

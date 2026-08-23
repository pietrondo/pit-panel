## 2025-02-18 - File Manager Table Accessibility
**Learning:** Attaching `@click` handlers directly to `<tr>` elements in interactive tables breaks keyboard accessibility because table rows are not natively focusable or actionable by keyboard users.
**Action:** Always wrap the primary action of a table row inside a native `<button>` element within the first `<td>`, ensuring keyboard users can tab to it and trigger it with Enter/Space.
## 2026-08-18 - Add autocomplete attributes to login and TOTP forms
**Learning:** Proper autocomplete attributes (like `one-time-code`, `username`, and `current-password`) are a major accessibility and UX win. For TOTP codes, `one-time-code` allows native keyboards (like iOS) and password managers to auto-suggest codes directly from SMS or authenticator apps, saving users significant friction.
**Action:** Always include appropriate `autocomplete` attributes on authentication and verification inputs to leverage built-in browser and OS autofill capabilities.
## 2026-08-23 - Add aria-current to active navigation items
**Learning:** Adding the  attribute to navigation items that are dynamically styled as "active" via JavaScript is a standard accessibility best practice. Without it, screen reader users may not be able to distinguish which link in a navigation list represents the page they are currently on.
**Action:** When writing scripts to apply visual  classes to navigation items based on the current URL path, ensure you simultaneously update the  attribute to provide proper semantic context for assistive technologies.
## 2026-08-23 - Add aria-current to active navigation items
**Learning:** Adding the `aria-current="page"` attribute to navigation items that are dynamically styled as "active" via JavaScript is a standard accessibility best practice. Without it, screen reader users may not be able to distinguish which link in a navigation list represents the page they are currently on.
**Action:** When writing scripts to apply visual `.active` classes to navigation items based on the current URL path, ensure you simultaneously update the `aria-current` attribute to provide proper semantic context for assistive technologies.

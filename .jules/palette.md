## 2025-02-18 - File Manager Table Accessibility
**Learning:** Attaching `@click` handlers directly to `<tr>` elements in interactive tables breaks keyboard accessibility because table rows are not natively focusable or actionable by keyboard users.
**Action:** Always wrap the primary action of a table row inside a native `<button>` element within the first `<td>`, ensuring keyboard users can tab to it and trigger it with Enter/Space.
## 2026-08-18 - Add autocomplete attributes to login and TOTP forms
**Learning:** Proper autocomplete attributes (like `one-time-code`, `username`, and `current-password`) are a major accessibility and UX win. For TOTP codes, `one-time-code` allows native keyboards (like iOS) and password managers to auto-suggest codes directly from SMS or authenticator apps, saving users significant friction.
**Action:** Always include appropriate `autocomplete` attributes on authentication and verification inputs to leverage built-in browser and OS autofill capabilities.
## 2024-05-19 - [Adding Loading States to Forms]
**Learning:** Found multiple places in the app where forms are submitted synchronously or asynchronously without giving visual feedback to the user, like a loading spinner or text change.
**Action:** Enhance user experience by adopting a standardized pattern for submitting states in forms using Alpine.js or HTMX to toggle a loading spinner and disable the submit button.

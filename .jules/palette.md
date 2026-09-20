## 2025-02-18 - File Manager Table Accessibility
**Learning:** Attaching `@click` handlers directly to `<tr>` elements in interactive tables breaks keyboard accessibility because table rows are not natively focusable or actionable by keyboard users.
**Action:** Always wrap the primary action of a table row inside a native `<button>` element within the first `<td>`, ensuring keyboard users can tab to it and trigger it with Enter/Space.
## 2026-08-18 - Add autocomplete attributes to login and TOTP forms
**Learning:** Proper autocomplete attributes (like `one-time-code`, `username`, and `current-password`) are a major accessibility and UX win. For TOTP codes, `one-time-code` allows native keyboards (like iOS) and password managers to auto-suggest codes directly from SMS or authenticator apps, saving users significant friction.
**Action:** Always include appropriate `autocomplete` attributes on authentication and verification inputs to leverage built-in browser and OS autofill capabilities.
## 2026-08-30 - Global button focus accessibility
**Learning:** In a heavily componentized application, generic `.btn` classes must explicitly define `:focus-visible` styles to ensure keyboard accessibility. Without a distinct focus ring (like `outline: 2px solid #6366f1; outline-offset: 2px;`), users navigating via keyboard cannot easily determine which element has focus.
**Action:** Always include global `:focus-visible` outline styles for buttons or interactive elements to ensure a clear keyboard focus state, improving a11y across the entire application without needing individual component updates.
## 2025-02-14 - Icon Buttons Missing Focus States
**Learning:** Custom icon-only buttons that don't use the design system's primary `.btn` class often lack keyboard focus indicators, making them invisible to keyboard navigation.
**Action:** Always manually add `focus:outline-none focus-visible:ring-2` to custom icon buttons (like modal close buttons or header toggles) to ensure consistent keyboard accessibility.
## 2024-11-20 - Screen Reader Accessibility for Site Builder Controls
**Learning:** Icon-only buttons (like `&times;` and `Del` buttons) inside dynamic components like Site Builder are read as "multiply" or unhelpful text by screen readers, creating accessibility barriers for users managing their sites.
**Action:** Always ensure that icon-only action buttons use descriptive `aria-label` attributes to clarify their purpose to assistive technologies (e.g. `aria-label="Remove widget"`).
## 2024-05-19 - [Adding Loading States to Forms]
**Learning:** Found multiple places in the app where forms are submitted synchronously or asynchronously without giving visual feedback to the user, like a loading spinner or text change.
**Action:** Enhance user experience by adopting a standardized pattern for submitting states in forms using Alpine.js or HTMX to toggle a loading spinner and disable the submit button.
## 2024-05-19 - [Third-Party CDN on Sensitive Pages]
**Learning:** Adding a third-party CDN dependency like Alpine.js to highly sensitive pages such as TOTP 2FA setup might be rejected for security reasons, even if it simplifies state management.
**Action:** When implementing UX improvements on sensitive security forms, prefer using native Javascript submit handlers or existing local libraries over introducing new external dependencies.

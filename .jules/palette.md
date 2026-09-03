## 2025-02-18 - File Manager Table Accessibility
**Learning:** Attaching `@click` handlers directly to `<tr>` elements in interactive tables breaks keyboard accessibility because table rows are not natively focusable or actionable by keyboard users.
**Action:** Always wrap the primary action of a table row inside a native `<button>` element within the first `<td>`, ensuring keyboard users can tab to it and trigger it with Enter/Space.
## 2026-08-18 - Add autocomplete attributes to login and TOTP forms
**Learning:** Proper autocomplete attributes (like `one-time-code`, `username`, and `current-password`) are a major accessibility and UX win. For TOTP codes, `one-time-code` allows native keyboards (like iOS) and password managers to auto-suggest codes directly from SMS or authenticator apps, saving users significant friction.
**Action:** Always include appropriate `autocomplete` attributes on authentication and verification inputs to leverage built-in browser and OS autofill capabilities.
## 2026-08-30 - Global button focus accessibility
**Learning:** In a heavily componentized application, generic `.btn` classes must explicitly define `:focus-visible` styles to ensure keyboard accessibility. Without a distinct focus ring (like `outline: 2px solid #6366f1; outline-offset: 2px;`), users navigating via keyboard cannot easily determine which element has focus.
**Action:** Always include global `:focus-visible` outline styles for buttons or interactive elements to ensure a clear keyboard focus state, improving a11y across the entire application without needing individual component updates.
## $(date +%Y-%m-%d) - File Input Accessibility
**Learning:** Using `class="hidden"` (`display: none`) on an `<input type="file">` within a customized file dropzone completely removes the element from the accessibility tree and prevents it from receiving keyboard focus. This makes the dropzone inaccessible to keyboard-only users who navigate via the Tab key.
**Action:** To style custom file upload dropzones while maintaining accessibility, use Tailwind's `.sr-only` class on the file input to visually hide it while keeping it focusable. Apply `.focus-within:ring-2` (and related outline/offset utilities) to the input's wrapping `<label>` so that when the invisible input receives focus, sighted keyboard users see a clear visual focus indicator on the visible label area.

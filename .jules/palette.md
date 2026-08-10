## 2025-02-18 - File Manager Table Accessibility
**Learning:** Attaching `@click` handlers directly to `<tr>` elements in interactive tables breaks keyboard accessibility because table rows are not natively focusable or actionable by keyboard users.
**Action:** Always wrap the primary action of a table row inside a native `<button>` element within the first `<td>`, ensuring keyboard users can tab to it and trigger it with Enter/Space.

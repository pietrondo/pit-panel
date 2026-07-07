## 2026-07-07 - Generic Text Button Ambiguity
**Learning:** Having multiple generic buttons (like "Copy" or "Clear") on the same page can be ambiguous for screen reader users, even if the text is visible.
**Action:** Always add descriptive `aria-label` attributes to generic buttons (e.g., `aria-label="Copy journal log"`) to provide clear context for assistive technologies.

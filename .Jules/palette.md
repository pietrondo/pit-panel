## 2024-05-18 - Missing ARIA label on delete button
**Learning:** Found a delete button lacking ARIA labels for screen readers in the file manager table, resulting in multiple generic "Delete" announcements without context.
**Action:** Adding specific aria-labels like `aria-label="\`Delete ${item.name}\`"` in loops helps contextualize icon-only or generic actions for a11y.

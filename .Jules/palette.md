## 2024-05-15 - Missing ARIA labels on modal close buttons
**Learning:** Found a recurring pattern where modal close buttons (e.g., in `file_manager.html`) only contain an SVG icon without any accessible text (`aria-label`). This poses an accessibility issue for screen reader users who cannot identify the purpose of the button.
**Action:** When adding or reviewing modals, always ensure that icon-only close buttons include an appropriate `aria-label` (e.g., `aria-label="Close"`).

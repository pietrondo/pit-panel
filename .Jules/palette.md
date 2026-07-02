## 2024-05-15 - Missing ARIA labels on modal close buttons
**Learning:** Found a recurring pattern where modal close buttons (e.g., in `file_manager.html`) only contain an SVG icon without any accessible text (`aria-label`). This poses an accessibility issue for screen reader users who cannot identify the purpose of the button.
**Action:** When adding or reviewing modals, always ensure that icon-only close buttons include an appropriate `aria-label` (e.g., `aria-label="Close"`).
## 2026-07-02 - Fix dizzying whole-button spinner
**Learning:** Applying an animation class (like Tailwind's `animate-spin`) directly to a parent container like a `<button>` affects the entire element and its text. Users find rotating text dizzying and unprofessional.
**Action:** Wrap icon elements inside a `<span class="inline-block">` and apply the animation directly to the `span` instead of the whole button. Additionally, properly add `:disabled="loading"` state to prevent multiple actions.

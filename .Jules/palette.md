## 2024-05-15 - Missing ARIA labels on modal close buttons
**Learning:** Found a recurring pattern where modal close buttons (e.g., in `file_manager.html`) only contain an SVG icon without any accessible text (`aria-label`). This poses an accessibility issue for screen reader users who cannot identify the purpose of the button.
**Action:** When adding or reviewing modals, always ensure that icon-only close buttons include an appropriate `aria-label` (e.g., `aria-label="Close"`).

## 2024-07-05 - Avoid spinning text in loading buttons
**Learning:** Found a button pattern where applying a spinning animation class (`animate-spin`) to the entire `<button>` element during a loading state causes the button text to spin along with the icon, creating a disorienting user experience.
**Action:** When implementing loading states on buttons containing both an icon and text, isolate the icon within a `<span class="inline-block">` (or `<svg>`) and apply the spinning animation class exclusively to that element to keep the text stable.

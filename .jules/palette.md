## 2024-05-24 - Alpine Dependencies in Standalone Pages
**Learning:** Standalone auth pages (like `login.html` and `setup_2fa.html`) do not inherit from the global `base.html` layout. Therefore, when introducing new interactive UI elements (like a password visibility toggle using Alpine.js), you must explicitly include the Alpine library `<script>` tag and necessary structural styles (like `[x-cloak]`) in the page's `<head>` to prevent raw content flashes and ensure interactivity works as expected.
**Action:** When adding Alpine-driven components to standalone entry points in this app, always verify that the page either extends a base layout with the required dependencies or includes them explicitly.
## 2024-06-27 - Refactor FastAPI Routes with Large Form Signatures
**Learning:** FastAPI endpoints that take numerous individual `Form()` parameters are difficult to maintain and read. Furthermore, inline sub-process calls inside async route handlers can be problematic.
**Action:** Encapsulate large form inputs using a `@dataclass` equipped with a `@classmethod def as_form(...)` for use with `Depends()`. When interacting with subprocesses like systemctl in async context, extract them to a dedicated manager and use `asyncio.create_subprocess_exec` instead of blocking `subprocess.run`.

## 2023-11-20 - Ensure Subprocess Call Wrappers Are Fully Tested
**Learning:** Utility functions that wrap native modules like `subprocess.run` often lack proper testing, reducing the reliability of debug/diagnostic endpoints. Ensure mock implementations return appropriate stand-in objects and handle exception paths gracefully.
**Action:** When adding tests for simple wrappers, create isolated mock paths for both standard behavior (e.g., successful process execution, empty stdouts) and error scenarios (e.g., exceptions raised inside the try-block). Always aim for 100% test coverage on these small utility files to prevent masking system-level faults.
## 2024-06-30 - Form Accessibility and UX in Jinja Templates
**Learning:** Explicit `for` and `id` linking for forms in templates combined with immediate UI feedback (like loading spinners in Alpine.js on forms) dramatically increases accessibility (for screen readers) and prevents duplicate submissions while providing a better UX.
**Action:** Always add explicit IDs/labels and `isSubmitting` tracking + loading states to primary action forms.

## 2024-06-25 - XSS in Direct HTMLResponse
**Vulnerability:** Unescaped raw log data outputted into an `HTMLResponse` directly instead of via Jinja2 template rendering.
**Learning:** Returning constructed HTML strings directly via FastAPI's `HTMLResponse` bypasses Jinja2's built-in `autoescape`, which creates an easy path for XSS payloads stored in logs to execute in the browser.
**Prevention:** Always manually sanitize dynamic/user-controlled data using `html.escape()` when constructing raw HTML responses in endpoints that do not use template rendering (or enforce standard template rendering where possible).

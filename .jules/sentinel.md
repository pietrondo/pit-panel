## 2024-03-22 - Prevent Caddyfile Directive Injection
**Vulnerability:** The `_sanitize` function previously mutated inputs by stripping dangerous characters (like quotes and newlines) silently, which could mask malicious intent or result in corrupted but parsable configurations.
**Learning:** Silently modifying user input (sanitization via mutation) is an anti-pattern for security. It can lead to bypasses if the regex isn't comprehensive, and doesn't clearly inform the caller that an injection attempt occurred.
**Prevention:** Always validate user input strictly and abort execution (e.g., raise an error or return HTTP 400 Bad Request) when forbidden characters or patterns are detected, rather than attempting to silently sanitize the input.

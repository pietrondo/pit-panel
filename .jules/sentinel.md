## 2025-02-28 - Caddyfile Directive Injection

**Vulnerability:** A Caddyfile Directive Injection vulnerability in `_get_acme_config` due to insufficient sanitization of `eab_key_id` and `eab_hmac` inputs in the `_sanitize` function.
**Learning:** Silently mutating user input (e.g. replacing quotes with empty strings) is dangerous because it can mask malicious intent and fail to account for other dangerous characters like newlines (`\n`, `\r`) which can lead to directive injection in configuration files.
**Prevention:** Strictly validate untrusted user input and fail closed by raising errors (e.g., ValueError) or aborting execution when forbidden characters or patterns are detected, rather than stripping or sanitizing them silently.

## 2026-06-26 - Caddyfile Directive Injection

**Vulnerability:** Caddyfile configuration injection via unescaped carriage return `\r` and newline `\n` characters, allowing malicious users to inject arbitrary Caddy directives.
**Learning:** Depending exclusively on Regex character classes like `r'[\r\n"{}']` in `re.sub` might be less clear than explicit `str.replace` sequences, or there could be a discrepancy with how literal strings or specific forms input parsing worked. Explicit replacements prevent any ambiguity in newline sanitation for Caddyfile directive escaping.
**Prevention:** Always use highly explicit sequences of `replace()` or strict whitelisting for configuration templates when interpolating user-controlled inputs. Additionally, write unit tests to explicitly verify injection payloads like `\r\n` are properly sanitized.

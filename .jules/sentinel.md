## 2026-06-26 - Caddyfile Directive Injection

**Vulnerability:** Caddyfile configuration injection via unescaped carriage return `\r` and newline `\n` characters, allowing malicious users to inject arbitrary Caddy directives.
**Learning:** Depending exclusively on Regex character classes like `r'[\r\n"{}']` in `re.sub` might be less clear than explicit `str.replace` sequences, or there could be a discrepancy with how literal strings or specific forms input parsing worked. Explicit replacements prevent any ambiguity in newline sanitation for Caddyfile directive escaping.
**Prevention:** Always use highly explicit sequences of `replace()` or strict whitelisting for configuration templates when interpolating user-controlled inputs. Additionally, write unit tests to explicitly verify injection payloads like `\r\n` are properly sanitized.
## 2024-05-24 - Input Validation for System and Docker Commands
**Vulnerability:** User inputs such as `api_token`, `container_id`, `base_domain`, and `panel_subdomain` were passed to system-level configuration files (Caddyfile, `.env`) and docker subprocess commands without strict sanitization.
**Learning:** This allowed potential command injection (via dashed prefixes to `docker` commands) or escaping configuration file formats (via newlines and quotes in `.env` files). Relying on client-side or implicit validation is insufficient when the inputs eventually hit the shell, docker daemon, or system configurations.
**Prevention:** Always implement strict server-side regex validation (e.g. `^[a-zA-Z0-9.-]+$`) for IDs and domain names, and explicitly block control characters and quotes (`\n`, `\r`, `"`, `'`) for tokens before writing them to configuration files or executing subprocess commands. Return an early 400 Bad Request to halt execution.
## 2026-10-24 - Environment Variable Escaping in .env

**Vulnerability:** User-controlled inputs (`api_var` and `api_token`) were written directly to `/etc/caddy/.env` without sanitization. This allowed attackers to inject newlines (`\n`) and quotes to escape the intended variable assignment and define arbitrary environment variables or execute commands if the file is sourced by a shell script.
**Learning:** Even when writing to configuration files rather than executing commands directly, unsanitized input can lead to severe security risks (like command injection or unauthorized configuration) when those files are parsed by other tools (like Caddy or bash).
**Prevention:** Always explicitly block and remove control characters (`\n`, `\r`) and quotes (`"`, `'`) from user inputs before interpolating them into environment variable configuration files (e.g., using explicit `.replace()` chains).

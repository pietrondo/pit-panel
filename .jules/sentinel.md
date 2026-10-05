## 2024-05-18 - Privilege Escalation via Sudo Password Injection
**Vulnerability:** The `run_cmd` and `run_sudo` functions in `src/pit_panel/core/sudo_ops.py` concatenate the application's configured `sudo_password` with the user-provided `input` (if any), and feed the combined string into the standard input of the executed `sudo` process. The intention is to answer the sudo password prompt, but if sudo doesn't consume the input (e.g. if the user uses `-n`, or if credentials are cached, or if NOPASSWD is set in `/etc/sudoers`), the remaining bytes (including the password) are passed into the *actual child process* running as root. This leaks the plaintext root password into the standard input of arbitrary commands like `tee`, `cat`, etc., which then process or echo the password.
**Learning:** Never pass a secret (like a password) into the generic `stdin` of a process chain where you cannot guarantee exactly which process will consume it. Sudo's `-S` reads from standard input, but if it doesn't need to read, the payload falls through to the executed command. This is a classic "CWE-522: Insufficiently Protected Credentials" resulting from improper stdin stream multiplexing.
**Prevention:** To safely use sudo with a password programmatically in an async context, first authenticate the user session using `sudo -S -p '' -v` (which specifically validates credentials and caches the token without running a child command). Once the token is cached, execute the desired child command normally with `sudo -n` (which relies on the cached token) and pass only the intended user data via `stdin`. Finally, invalidate the token with `sudo -K`.

## 2024-05-20 - Insecure File Upload Handling / Resource Exhaustion
**Vulnerability:** The `upload_file` endpoint in `src/pit_panel/web/routes/file_manager.py` processed file uploads using `asyncio.to_thread` wrapping `shutil.copyfileobj(file.file, f)`. For large file uploads, this synchronous I/O can block thread pool workers and cause memory exhaustion or application slowdowns (DoS).
**Learning:** When dealing with asynchronous Python web frameworks (like FastAPI), file operations shouldn't be naively offloaded to threads if they involve potentially unbound data copying from SpooledTemporaryFiles, as they still load large objects or block execution in ways that evade typical async resource management.
**Prevention:** Always use `aiofiles.open` inside an `async with` context and perform chunked asynchronous reads (`await file.read(chunk_size)`) to stream file uploads to disk safely without blocking the event loop or consuming excessive memory.

## 2024-08-09 - Path Traversal via string startswith()
**Vulnerability:** The `_safe_path` function in `src/pit_panel/web/routes/debug_api.py` used `str(p).startswith(prefix)` to check if a path was within an allowed directory. This allows paths like `/opt/pit-panel-hacked/test` to bypass the check because the string starts with `/opt/pit-panel`.
**Learning:** Using string matching like `.startswith()` for path validation is dangerous and leads to path traversal / authorization bypass vulnerabilities because it ignores directory boundaries.
**Prevention:** Always use proper path manipulation libraries for authorization checks. In Python, use `pathlib.Path` methods like `p.is_relative_to(allowed_root)` after fully resolving both the target path and the allowed root path.
## 2026-09-01 - Strict regex + IP canonicalization
**Vulnerability:** Input validation for fail2ban jails, container names and subdomains relied on `re.match`, allowing a trailing newline to bypass the check. Separately, IPs for `iptables` were validated but passed as uncanonicalized strings.
**Learning:** `re.match` only anchors the start of the string, and even with `$` it matches *just before* a trailing newline. For atomic entities (hostnames, identifiers) that is a validation bypass. IP strings must also be canonicalized before reaching shell tools.
**Prevention:** Always use `re.fullmatch` for strict validation, and pass IPs through `ipaddress.ip_network(ip).compressed` before using them in system commands. Applies to `_validate_subdomain` (`src/pit_panel/core/app_manager.py`), fail2ban jail names and container names.

## 2024-05-22 - Path Traversal via re.match() Validation Bypass
**Vulnerability:** The `_validate_subdomain` function in `src/pit_panel/core/app_manager.py` used `_SUBDOMAIN_RE.match(subdomain)` to validate subdomain inputs. In Python, `re.match` anchors only to the start of the string. Even if the regex pattern ends with `$`, it allows a trailing newline character. Thus, malicious subdomains containing a trailing newline (e.g. `valid\nmalicious`) could bypass validation and potentially exploit downstream path construction or command execution.
**Learning:** `re.match` is insufficient for strict string validation when the input represents an atomic entity (like a hostname, path, or identifier) rather than a stream of text lines.
**Prevention:** Always use `re.fullmatch` when performing strict string validation to enforce that the entire input matches the pattern without any hidden trailing characters.

## 2024-09-14 - CSRF Bypass via startswith()
**Vulnerability:** The CSRF middleware validated the `Referer` header using `referer.startswith(expected_origin)`. This allows an attacker on `https://example.com.malicious.com` to bypass the CSRF check since the string starts with `https://example.com`.
**Learning:** Using string matching like `.startswith()` for URL validation is dangerous and can lead to SSRF or CSRF bypasses because it ignores URI boundaries like the end of the domain name.
**Prevention:** Always use proper URL parsing libraries like `urllib.parse.urlparse` to extract and strictly compare the `scheme` and `netloc` components when validating origins and referers.
## 2024-08-30 - re.match with ^...$ is not strict validation
**Vulnerability:** Backend routes validated container names, domains and app names with `re.match(r"^...$", ...)`. In Python `$` matches the end of the string *or just before a trailing newline*, so `container_name\n` passed validation and then reached `subprocess` unfiltered.
**Learning:** Anchors do not save you: `^`/`$` are line anchors, not string anchors. `\A`/`\Z` are the string-level ones, and `re.fullmatch` is the readable form of the same intent.
**Prevention:** `re.fullmatch` everywhere you validate an atomic value that will reach a command line.

## 2026-09-27 - Fix CSRF bypass via path startswith
**Vulnerability:** CSRF protection could be bypassed due to improper path matching (`request.url.path.startswith(p)`).
**Learning:** `startswith` allows bypassing protection by appending characters to an exempt path (e.g., `/login-malicious` matches `/login`).
**Prevention:** Always use exact matching or ensure directory boundaries (e.g., `p + "/"`) when matching paths for security exemptions.

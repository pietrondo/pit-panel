🔒 Fix CRLF Injection in AbuseIPDB HTTP Client

🎯 **What:** The `_abuseipdb_check` and `_abuseipdb_blacklist` functions in `src/pit_panel/web/routes/security.py` were vulnerable to CRLF (Carriage Return Line Feed) injection. The inputs `ip` and `api_key` were being interpolated into the HTTP request path and headers without sufficient sanitization at the `conn.request` and `headers` assignment level.

⚠️ **Risk:** `http.client` is known to be vulnerable to CRLF injection if inputs aren't sanitized. An attacker could inject `\r\n` characters into the `api_key` or `ip` parameter, allowing them to manipulate the HTTP request, inject malicious headers, or potentially influence subsequent responses (HTTP Request Smuggling/Splitting), leading to severe security compromises depending on how the upstream server processes the malformed request.

🛡️ **Solution:** The fix implements inline sanitization using `.replace("\r", "").replace("\n", "")` directly where the variables are used in the `headers` dictionary and the `conn.request` URL string for both functions. A unit test `test_abuseipdb_blacklist_crlf_mitigation` was also added to ensure that headers remain clean and `\r\n` characters are properly stripped before the request is dispatched.

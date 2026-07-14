## 2024-07-15 - SSRF in fetch_blocklist
**Vulnerability:** Potential Server-Side Request Forgery in fetch_blocklist where arbitrary URLs could be requested.
**Learning:** User or external input should not be directly passed to functions that perform network requests without strict validation against a known allowlist.
**Prevention:** Always validate URLs against an explicit allowlist before making network requests.

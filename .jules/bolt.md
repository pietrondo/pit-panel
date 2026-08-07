## 2024-05-19 - [Bounded TTL Cache for High-Frequency IP Ban Checks]
**Learning:** Adding a raw, unbounded dictionary cache to a high-frequency middleware check like `is_ip_banned` creates a critical OOM DoS vulnerability, since it caches all requests (even non-banned spoofed IPs) permanently.
**Action:** When caching security or networking checks globally in memory, always use a bounded structure (like `cachetools.TTLCache`) configured with a strict `maxsize` to ensure safety and prevent uncontrolled growth.

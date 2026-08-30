## 2024-07-19 - Optimize Database Inserts in Settings
**Learning:** Replacing repeated `db.add()` calls in a loop with a single `db.add_all()` call significantly improves database insertion performance in SQLAlchemy (measured ~52% improvement for 1000 items).
**Action:** Always accumulate objects in a list during loops and use `db.add_all()` for bulk insertions to minimize overhead and improve efficiency.
## 2024-05-24 - Cache session serializer instance
**Learning:** Instantiating `URLSafeTimedSerializer` on every request (via `get_user`) adds significant overhead. The instance is thread-safe and stateless with respect to keys.
**Action:** Cache the serializer instance at the module level to reuse it across requests.

## 2024-07-21 - Batch systemctl is-active queries
**Learning:** Sequential calls to 'systemctl is-active' via sudo incur significant overhead (e.g. ~30ms vs ~7ms) due to subprocess and authentication latency. 'systemctl is-active' natively supports multiple services as arguments and returns newline-separated results.
**Action:** Always batch 'systemctl is-active' checks by passing all service names as arguments to a single call and splitting the output by newline.
## 2024-10-24 - Avoid thread pool overhead for static returns
**Learning:** Offloading fast synchronous functions returning static cached data to `asyncio.to_thread` introduces significant context-switching overhead on high-frequency polling routes.
**Action:** Call static or fast synchronous lookup functions directly on the main thread rather than wrapping them in a thread pool executor.
## 2024-05-24 - Async File I/O Optimization
**Learning:** Writing files synchronously (e.g., using `open()` or `asyncio.to_thread(_save_file)` with large chunks) within an async endpoint like `/api/file-manager/upload` blocks the event loop and scales poorly under concurrency, causing bottlenecks.
**Action:** Replace synchronous file writing loops and `asyncio.to_thread` with non-blocking alternatives like `aiofiles.open()` in an `async with` block alongside asynchronous file reading (e.g., `await file.read()`).
<<<<<<< HEAD
## 2024-05-24 - Async to_thread Context Switching Overhead
**Learning:** Using `asyncio.to_thread` for very fast, synchronous operations like reading small pseudo-files (`/proc/loadavg`, `/proc/meminfo`) on high-frequency polling routes incurs significant context-switching overhead (~18x slower in benchmarks) that far outweighs the benefit of offloading to a thread.
**Action:** Call fast, non-blocking synchronous file reads directly on the main thread rather than wrapping them in `asyncio.to_thread` when in hot code paths.
## 2024-10-24 - Optimize File Parsing with .startswith()
**Learning:** Using `.split()` on every line during file parsing (like `/proc/meminfo`) creates unnecessary list objects and slows down high-frequency loops.
**Action:** Use `.startswith()` on strings directly before attempting to extract or split data to avoid unnecessary memory allocations and improve CPU execution time during parsing.
## 2024-07-31 - Overhead of asyncio.to_thread on fast I/O
**Learning:** Wrapping very fast, synchronous operations (like reading `/proc/loadavg` or `/proc/meminfo`) in `asyncio.to_thread` introduces significant thread-switching overhead (~1ms per call) that far exceeds the time it takes to execute the operation synchronously (~0.05ms), especially on high-frequency HTMX polling routes.
## 2025-02-12 - In-Memory Cache for DB Queries in Fast Polling Routes
**Learning:** High-frequency polling endpoints (like HTMX updating every 10 seconds) execute identical database queries for each connected client unnecessarily. Uncached repetitive DB polling creates bottlenecks.
**Action:** Implement a short-lived in-memory cache using a bounded dictionary structure with a manual `MAX_CACHE_SIZE` limit and TTL checks via `time.monotonic()` for global data fetched on high-frequency routes to reduce DB load.
## 2026-08-12 - In-Memory Cache for DB Queries in Middleware Security Checks
**Learning:** High-frequency polling endpoints and middleware (like `_ip_ban_middleware`) execute identical database queries for each connected client unnecessarily. Uncached repetitive DB polling creates bottlenecks.
**Action:** Implement a short-lived in-memory cache using a bounded dictionary structure with a manual `MAX_CACHE_SIZE` limit and TTL checks via `time.monotonic()` for global data fetched on high-frequency routes or middleware to reduce DB load, ensuring to clear the cache upon updates.
## 2025-02-12 - Skip DB Session Creation for Middleware Cache Hits
**Learning:** Even when `is_ip_banned` utilizes an in-memory cache, instantiating the SQLAlchemy database session in middleware (`async with sessionmaker() as db:`) on every request takes significant overhead (~9ms vs ~0.06ms). Bypassing DB session creation entirely when an IP is already cached and valid dramatically speeds up middleware execution for cache hits.
**Action:** When using in-memory caching for database queries in middleware (like IP banning), extract the cache-checking logic to a fast, synchronous path that executes *before* establishing the database session context.

## 2026-08-17 - Expensive Security Object Instantiation in Hot Paths
**Learning:** Dynamically instantiating `itsdangerous.URLSafeTimedSerializer` on every authenticated request (via dependency injection) adds ~0.5ms overhead per request. This was happening in `get_current_user` despite a cached serializer existing in `auth.py`.
**Action:** Always reuse security object instances (serializers, hashers, etc.) across requests, especially in authentication middleware or global dependencies. Check for existing cached singletons before instantiating inline.
## 2025-02-12 - O(1) in-memory RateLimiter cleanup fast-path
**Learning:** The in-memory cache implementation of `RateLimiter` executed an O(N) cleanup loop across all keys on every invocation of `is_allowed`. For high-frequency requests, this global loop blocks CPU cycles unnecessary.
**Action:** Always optimize per-request rate limiters and cache evictions by lazily cleaning only the currently accessed key during the hot path, and deferring global garbage collection over the entire cache to periodic intervals (e.g., matching the expiration window).

## 2025-02-12 - Update session token_hash to match cookie
**Learning:** Found an existing fetch-and-update pattern (`select()` followed by modifying object and `commit()`) that was redundant because the session record already had the correct `token_hash` when it was created. Even if we had to update it, using a direct SQLAlchemy `update()` statement is more efficient than the fetch-and-update pattern because it avoids a redundant database read.
**Action:** Replaced the fetch-and-update pattern with a direct `update()` statement.
## 2024-06-25 - Optimize IP ban counting and expired ban cleanup
**Learning:** Found two common unoptimized patterns in SQLAlchemy: 1) fetching all matching row objects just to compute their count using `len()` which causes heavy N+1 object hydration latency on large tables. 2) Using a SELECT to get row objects, and then running a DELETE loop `for obj in expired: await db.delete(obj)`, which causes severe N+1 latency over the network.
**Action:** Always prefer DB-side aggregations (`func.count()`) instead of counting records in application memory. For deletion, use single-query bulk deletion syntax (`delete(Model).where(...)`) instead of individual deletions loop.
## 2025-02-18 - Optimized regex parsing in Caddy certificates
**Learning:** Compiling regex patterns that are heavily used inside loops (such as parsing large PEM texts) can yield performance improvements. In `src/pit_panel/core/caddy.py`, inline regex compilations in the `_parse_pem_certs` loop slowed down certificate extraction unnecessarily.
**Action:** Lifted regex pattern compilation to the module level as `_PEM_CERT_PATTERN`, `_WHITESPACE_PATTERN`, and `_DER_EXPIRY_PATTERN`. This resulted in a ~8% performance improvement on repeated parsing without breaking existing parsing logic.
## 2023-11-20 - Optimize Blocklist Import
**Learning:** Iterating through fetched blocklist IPs and awaiting `ban_ip` per IP creates a severe N+1 query overhead, particularly noticeable on large IP lists.
**Action:** Replaced the loop in `daily_blocklist_import` with a single `ban_ips_bulk` function that performs a bulk IN query to find existing IPs and a bulk `add_all` insert, improving performance by >4x.
## 2025-02-18 - Optimize Dashboard Counts without extra queries
**Learning:** Found a case where in-memory counts (`len()`) on a small limited dataset (`limit(20)`) were replaced with additional `func.count()` queries, which acts as an anti-optimization because it adds network round-trip overhead.
**Action:** Do not use `func.count()` to replace in-memory counting of small datasets if it requires adding *extra* queries. When full table counts are required for statistics alongside limited lists, use conditional aggregation (e.g., `func.count(Model.id).filter(...)`) combined into a single query to minimize network round-trips.

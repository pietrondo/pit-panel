## 2024-07-19 - Optimize Database Inserts in Settings
**Learning:** Replacing repeated `db.add()` calls in a loop with a single `db.add_all()` call significantly improves database insertion performance in SQLAlchemy (measured ~52% improvement for 1000 items).
**Action:** Always accumulate objects in a list during loops and use `db.add_all()` for bulk insertions to minimize overhead and improve efficiency.
## 2024-05-24 - Cache session serializer instance
**Learning:** Instantiating `URLSafeTimedSerializer` on every request (via `get_user`) adds significant overhead. The instance is thread-safe and stateless with respect to keys.
**Action:** Cache the serializer instance at the module level to reuse it across requests.

## 2024-07-21 - Batch systemctl is-active queries
**Learning:** Sequential calls to 'systemctl is-active' via sudo incur significant overhead (e.g. ~30ms vs ~7ms) due to subprocess and authentication latency. 'systemctl is-active' natively supports multiple services as arguments and returns newline-separated results.
**Action:** Always batch 'systemctl is-active' checks by passing all service names as arguments to a single call and splitting the output by newline.

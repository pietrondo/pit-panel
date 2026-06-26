## 2025-02-12 - Update session token_hash to match cookie
**Learning:** Found an existing fetch-and-update pattern (`select()` followed by modifying object and `commit()`) that was redundant because the session record already had the correct `token_hash` when it was created. Even if we had to update it, using a direct SQLAlchemy `update()` statement is more efficient than the fetch-and-update pattern because it avoids a redundant database read.
**Action:** Replaced the fetch-and-update pattern with a direct `update()` statement.

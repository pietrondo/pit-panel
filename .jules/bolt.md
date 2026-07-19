## 2024-05-24 - Async File I/O Optimization
**Learning:** Writing files synchronously (e.g., using `open()` or `asyncio.to_thread(_save_file)` with large chunks) within an async endpoint like `/api/file-manager/upload` blocks the event loop and scales poorly under concurrency, causing bottlenecks.
**Action:** Replace synchronous file writing loops and `asyncio.to_thread` with non-blocking alternatives like `aiofiles.open()` in an `async with` block alongside asynchronous file reading (e.g., `await file.read()`).

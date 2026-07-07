## 2024-05-18 - Optimize _detect_ssh_port
**Learning:** Using `open().read()` inside an async function directly blocks the asyncio event loop, severely degrading concurrency when multiple requests hit routes triggering the function. Refactoring it to run inside a separate thread is necessary to restore non-blocking I/O.
**Action:** Always wrap synchronous file operations (like `open().read()` or `Path.read_text()`) inside `await asyncio.to_thread(func)` or use `aiofiles` when writing asynchronous Python code to prevent blocking the event loop.

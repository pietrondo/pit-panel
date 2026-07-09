## 2024-05-18 - Optimize _detect_ssh_port
**Learning:** Using `open().read()` inside an async function directly blocks the asyncio event loop, severely degrading concurrency when multiple requests hit routes triggering the function. Refactoring it to run inside a separate thread is necessary to restore non-blocking I/O.
**Action:** Always wrap synchronous file operations (like `open().read()` or `Path.read_text()`) inside `await asyncio.to_thread(func)` or use `aiofiles` when writing asynchronous Python code to prevent blocking the event loop.


## 2024-05-18 - Optimize Dashboard Stats with Concurrent Non-Blocking I/O
**Learning:** Calling synchronous file I/O operations (like `open().read()` or `shutil.disk_usage()`) inside `async def` FastAPI routes blocks the asyncio event loop. In `dashboard.py`, these were running serially.
**Action:** When multiple independent I/O tasks are required in a route, wrap the synchronous ones in `asyncio.to_thread()` and await them concurrently using `asyncio.gather()` alongside other async tasks (like `docker_mgr.containers_count()`) to minimize route latency and prevent blocking the server. Ensure that multiple database queries on the same session are grouped in a single async helper before passing them to `asyncio.gather()` to prevent concurrent connection errors.

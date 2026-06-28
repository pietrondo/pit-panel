🧹 [Code Health] Enhance documentation for CaddyfileConfig and _generate_caddyfile

🎯 **What:** Added descriptive docstrings to the `CaddyfileConfig` dataclass and the `_generate_caddyfile` function in `src/pit_panel/web/routes/ssl.py`. Also applied standard ruff formatting to `ssl.py`, `caddy.py`, and related tests.
💡 **Why:** The issue requested grouping the arguments of `_generate_caddyfile` into a model. Since this refactoring was already present in the codebase, the docstrings and formatting were added as a fallback code health improvement to further enhance maintainability and readability.
✅ **Verification:** Verified by running `uv run ruff check --fix src tests` and running the full test suite (`uv run pytest`) to ensure no regressions were introduced.
✨ **Result:** Improved documentation and consistent code formatting, making the codebase easier to read and maintain without altering any functionality.

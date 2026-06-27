## 🧹 Explicitly register web routers

🎯 **What:**
Refactored `src/pit_panel/web/app.py` to remove unused imports that relied on side effects. Each route module now defines its own `fastapi.APIRouter()`, and `app.py` explicitly imports and registers each router via `app.include_router()`. The shared rate `limiter` was extracted into `src/pit_panel/web/limiter.py` to prevent circular dependencies.

💡 **Why:**
Relying on import side effects is poor practice because it obfuscates dependencies and makes code harder to maintain and test. Explicit router registration makes the application structure clearer and immediately understandable.

✅ **Verification:**
- The refactored code passes `uv run ruff format` and `uv run ruff check`.
- All tests pass via `uv run pytest`.
- Manual verification of routers correctly instantiating and appending to FastAPI's instance.

✨ **Result:**
Cleaner, more maintainable code with no unused imports or side-effect-driven initialization.

1. **Analyze the Issue**:
   - `app_deploy` function in `src/pit_panel/web/routes/app_routes/main.py` is overly complex and exceeds 100 lines (code health issue).
   - It performs subdomain resolution, rendering fallback views on error, Docker Compose deployment, WordPress auto-setup, and Caddy reverse proxy setup all in one monolith.

2. **Refactor**:
   - Extracted parts of the function into smaller, well-named helper functions:
     - `_resolve_subdomain`: Handles logic to retrieve or create a Subdomain record.
     - `_render_apps_error`: Prepares context and renders `apps.html` when an error occurs before deploy.
     - `_auto_setup_wordpress`: Sets up WordPress via WP-CLI inside the container if it's a WordPress stack.
     - `_setup_caddy_route`: Calls CaddyManager to create subdomain or main domain routes.
   - Refactored `app_deploy` to use these helpers, reducing its size significantly.

3. **Verify**:
   - Verified that `uv run ruff check` runs clean (after fixing long lines and formatting).
   - Verified that `uv run pytest tests/unit/test_web_routes.py` and `tests/unit/test_app*.py` pass.

4. **Document**:
   - I will submit the code change using the `submit` tool on a new branch with a PR detailing the code health improvement.

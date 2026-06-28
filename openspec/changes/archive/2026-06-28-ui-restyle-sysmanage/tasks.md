# Tasks: UI Restyling & SysManage Integration

## Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Phase 1: Foundation
- [x] Extend Tailwind configuration in [base.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/base.html) to include new colors and Outfit/Inter/JetBrains Mono Google Fonts.
- [x] Create template file `src/pit_panel/web/templates/partials/_app_status.html` with Tailwind badges for Active/Inactive and container status counts.

## Phase 2: Backend
- [x] Add async GET `/apps/{sd_id}/status` route in [apps.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/apps.py) querying database and DockerManager.
- [x] Support retrieving subdomain status dynamically, counting total and active (Status: "Up") containers.

## Phase 3: Frontend
- [x] Add DOMContentLoaded active route highlight JavaScript to [base.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/base.html) using data-path checks.
- [x] Update [apps.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/apps.html) cards with lazy HTMX status loader, active inputs disabled status during submission, and hover animations.
- [x] Update [system_manage.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/system_manage.html) with Alpine.js tabs visual styling.
- [x] Replace plain system status output in [system_manage.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/system_manage.html) with the styled retro terminal emulator window skin.
- [x] Implement Alpine-controlled double-confirmed reboot buttons preventing accidental clicks on system page.

## Phase 4: Verification
- [x] Add unit tests in `tests/unit/test_system_manage.py` and `tests/unit/routes/test_security_route.py` or similar.
- [x] Run linter `uv run ruff check src/ tests/` and verify all tests pass with `uv run pytest`.

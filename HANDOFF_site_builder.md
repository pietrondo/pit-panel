# Site Builder — Handoff

## What was built

A drag&drop visual editor for static sites, integrated as `/site-builder` inside pit-panel.

- **Route module**: `src/pit_panel/web/routes/site_builder.py`
- **Templates**: `site_builder.html` (list), `site_builder_edit.html` (editor)
- **DB model**: `Site` in `src/pit_panel/db/models.py`
- **Migration**: `alembic/versions/a1b2c3d4e5f6_add_sites_table.py`
- **Nav menu**: link added in `base.html` between Apps and Containers
- **Tests**: `tests/unit/test_site_builder.py` (17 tests, all passing)

## Architecture (MVP bare-bones)

```
Browser ──► FastAPI route /site-builder/...
                  │
                  ├─ SQLite (Site model with widgets_json JSON column)
                  │
                  └─ On publish: writes static HTML to
                     /var/lib/pit-panel/published-sites/{subdomain}/index.html
```

- **Frontend**: Alpine.js (already loaded in pit-panel base template) + SortableJS 1.15 (CDN, deferred)
- **Auth**: `get_admin` middleware (same as other pit-panel routes)
- **Widget types**: heading, text, image, button, divider
- **Widget tree storage**: JSON column on `Site.widgets_json`, validated/coerced server-side

## How to test manually

1. Run migrations: `uv run alembic upgrade head`
2. Start pit-panel: `uv run python -m pit_panel`
3. Log in as admin
4. Click **Site Builder** in sidebar
5. Create a site (name only)
6. Drag&drop: click widgets in left sidebar to add, drag within/between columns to reorder, click column headers to change width (1-12), inline edit fields update properties
7. Click **Publish** → writes HTML to `/var/lib/pit-panel/published-sites/{subdomain}/index.html`

## Known limitations (deliberate MVP scope cuts)

| Out of scope (this MVP) | Why | Future work |
|---|---|---|
| Responsive preview (mobile/tablet) | Bare-bones scope | Add breakpoint preview tabs |
| Style panel (colors, fonts per widget) | Bare-bones scope | CSS variables bound per widget |
| Template library | Bare-bones scope | Add `_templates` table, picker UI |
| Multi-page sites (one page = one site) | Bare-bones scope | Add `Page` model with route suffix |
| Form widget | Bare-bones scope | Add backend handler for form submissions |
| Revision history | Bare-bones scope | Add `SiteRevision` table + diff UI |
| Caddy subdomain auto-route | Out of MVP scope | See "Next steps" below |

## Next steps (in priority order)

1. **Integration tests**: scaffold `TestClient` for site_builder endpoints with admin auth mock (currently only unit tests for tree validation/widget rendering).
2. **Image upload widget**: replace image URL input with file upload using existing `pit_panel.web.routes.file_manager` upload endpoint.
3. **CSS variables per widget**: minor change in `render_site_html` to merge per-widget style props.
4. **Preview mode**: render the static HTML in an iframe inside the editor for WYSIWYG feedback.
5. **Multi-page support**: add `Page` model with route suffix.

## What changed for existing users

- **Nav menu**: new "Site Builder" item visible to admins (between Apps and Containers).
- **DB**: new `sites` table. No impact on existing data. `alembic upgrade head` is the only required action.
- **No new dependencies**: Alpine.js was already loaded; SortableJS is loaded from CDN (jsDelivr) inside `site_builder_edit.html`.
- **No port or config changes**.
- **Caddy**: on publish, `CaddyManager.add_static_subdomain()` is called if `settings.base_domain` is set; it adds a `file_server` route for the subdomain. On delete, the route is removed.

## Files added / modified

```
modified:  src/pit_panel/db/models.py                          (+22 lines, Site model)
modified:  src/pit_panel/web/app.py                            (+2 lines, router import + include)
modified:  src/pit_panel/web/routes/__init__.py                (+2 lines, export site_builder_router)
modified:  src/pit_panel/web/templates/base.html               (+7 lines, nav menu)
modified:  src/pit_panel/core/caddy.py                         (+24 lines, add_static_subdomain + remove_static_subdomain)
modified:  src/pit_panel/web/routes/site_builder.py            (~330 lines, with Caddy integration)
new:       src/pit_panel/web/templates/site_builder.html       (~70 lines)
new:       src/pit_panel/web/templates/site_builder_edit.html  (~290 lines)
new:       alembic/versions/a1b2c3d4e5f6_add_sites_table.py    (~50 lines)
new:       tests/unit/test_site_builder.py                     (~210 lines, 17 tests)
new:       tests/unit/test_caddy_static.py                     (~70 lines, 3 tests)
```

## Verification commands

```bash
# Lint
uv run ruff check src/ tests/

# Tests
uv run pytest -q tests/unit/test_site_builder.py
uv run pytest -q tests/unit/test_caddy_static.py

# Full suite (779 tests, no regressions)
uv run pytest -q tests/unit

# DB migration
uv run alembic upgrade head
```

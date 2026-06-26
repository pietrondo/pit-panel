# Main Domain App — Design Doc

## Objective

Allow deploying a containerized app directly on the **naked base domain** (`example.com`),
in addition to the existing subdomain-based apps (`app.example.com`).

The admin panel stays at `panel.{domain}` — unchanged.

## Data Model

### Subdomain table — new field

```python
is_main_domain: Mapped[bool] = mapped_column(default=False)
```

- Max **1** record with `is_main_domain=True` per `base_domain`
- When `is_main_domain=True`, `subdomain` is auto-set to `"_main_"` (internal, hidden in UI)
- The FQDN becomes `{base_domain}` instead of `{subdomain}.{base_domain}`

## Caddy — New Methods

### `caddy.py`

```python
async def add_main_domain(self, base_domain: str, port: int = 80):
    route = {
        "@id": f"main-{base_domain}",
        "match": [{"host": [base_domain]}],
        "handle": [{
            "handler": "reverse_proxy",
            "upstreams": [{"dial": f"127.0.0.1:{port}"}]
        }],
    }
    return await self._patch_routes(route)

async def remove_main_domain(self, base_domain: str):
    return await self._delete_route(f"main-{base_domain}")
```

Route `@id` uses `main-` prefix to avoid collision with subdomain routes. Panel is
unchanged at `panel.{domain}`.

## Deploy Flow

### UI — `apps.html`

Checkbox in deploy form: **"Deploy on main domain"**.
When checked, `new_subdomain` / `subdomain_id` fields are ignored/hidden.

### Route — `POST /apps/deploy`

When `is_main_domain=True`:

1. **Check existing**: query for existing `Subdomain` with `is_main_domain=True`.
   If found → error "Main domain app already deployed".
2. **Create Subdomain**: `subdomain="_main_"`, `base_domain=settings.base_domain`,
   `is_main_domain=True`, `owner_user_id=user.id`.
3. **Deploy template**: `mgr.deploy_template("_main_", stack_type, variables)`.
   Files go to `/opt/pit-panel/apps/_main_/`.
4. **Docker compose**: `docker_mgr.compose_up("_main_")`.
5. **Caddy route**: `caddy.add_main_domain(settings.base_domain, port=port)`.

### Route — `POST /apps/{sd_id}/delete`

When `sd.is_main_domain=True`:

1. `docker_mgr.compose_down("_main_", remove_volumes=True)`.
2. `caddy.remove_main_domain(sd.base_domain)`.
3. `mgr.delete_app("_main_")`.
4. Reset `sd.app_type = None` (or delete the record).

### Restart / Stop

Same as subdomain apps — just use `"_main_"` as the directory name.

## UI Changes

### `apps.html` — list page
- Main domain app shown with badge **"Main Domain"**
- `_main_` subdomain name hidden, display URL as `{base_domain}`
- Subdomain list excludes `_main_` records (or shows them in a separate section)

### `app_detail.html` — detail page
- Show URL as `{base_domain}` (not `_main_.{base_domain}`)
- Badge "Main Domain" next to the app name

### `subdomains.html`
- `_main_` records excluded from CRUD list (managed only from Apps section)

## Constraints

| Rule | Enforcement |
|------|-------------|
| Max 1 main domain app per base_domain | Check in deploy endpoint |
| Panel stays at `panel.{domain}` | Unchanged — separate Caddy route |
| `_main_` subdomain not user-editable | Hidden from subdomain forms |
| Main domain Caddy route removed on delete | Called in `app_delete` |

## Files Changed

| File | Changes |
|------|---------|
| `src/pit_panel/db/models.py` | Add `is_main_domain` column to `Subdomain` |
| `src/pit_panel/core/caddy.py` | Add `add_main_domain()`, `remove_main_domain()` |
| `src/pit_panel/web/routes/apps.py` | Handle `is_main_domain` in deploy/delete |
| `src/pit_panel/web/routes/subdomains.py` | Exclude `_main_` from subdomain list |
| `src/pit_panel/web/templates/apps.html` | Checkbox in form, badge in list |
| `src/pit_panel/web/templates/app_detail.html` | Show `{base_domain}` instead of FQDN |
| `tests/unit/routes/test_apps.py` | Tests for main domain deploy/delete |

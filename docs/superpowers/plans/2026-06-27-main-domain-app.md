# Main Domain App — Implementation Plan

> **For agentic workers:** Execute tasks in order. Each task produces independent, testable changes.

**Goal:** Allow deploying containerized apps on the naked base domain (`example.com`) in addition to subdomains.

**Approach:** Add `is_main_domain` flag to `Subdomain` model; new Caddy methods for main-domain route; deploy/delete logic in apps routes; UI checkbox + badge.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, Jinja2, HTMX, Caddy admin API

---
### Task 1: DB Model — add `is_main_domain` column

**Files:**
- Modify: `src/pit_panel/db/models.py:46-63`

**Step 1:** Add column after `status`

```python
is_main_domain: Mapped[bool] = mapped_column(default=False)
```

**Step 2:** Run tests

```bash
uv run pytest -q
```

**Step 3:** Commit

```bash
git add src/pit_panel/db/models.py && git commit -m "feat: add is_main_domain column to Subdomain"
```

### Task 2: Caddy — main domain methods

**Files:**
- Modify: `src/pit_panel/core/caddy.py`

**Step 1:** Add methods to `CaddyManager`, after `setup_panel_route` (line 70):

```python
async def add_main_domain(
    self, base_domain: str, port: int = 80
) -> dict[str, Any]:
    route = {
        "@id": f"main-{base_domain}",
        "match": [{"host": [base_domain]}],
        "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{port}"}]}],
    }
    return await self._patch_routes(route)

async def remove_main_domain(self, base_domain: str) -> dict[str, Any]:
    return await self._delete_route(f"main-{base_domain}")
```

**Step 2:** Commit

```bash
git add src/pit_panel/core/caddy.py && git commit -m "feat: add_main_domain/remove_main_domain Caddy methods"
```

### Task 3: Deploy route — handle main domain

**Files:**
- Modify: `src/pit_panel/web/routes/apps.py:68-210`

**Step 1:** Add `is_main_domain: bool = Form(False)` to `app_deploy` signature.

**Step 2:** After existing subdomain resolution (line 118), add main-domain logic:

```python
if is_main_domain:
    existing = await db.execute(
        select(Subdomain).where(
            Subdomain.is_main_domain == True,
            Subdomain.base_domain == settings.base_domain,
        )
    )
    if existing.scalar_one_or_none():
        error = "Main domain app already deployed"
    else:
        sd = Subdomain(
            subdomain="_main_",
            base_domain=settings.base_domain,
            owner_user_id=user.id,
            is_main_domain=True,
        )
        db.add(sd)
        await db.flush()
```

**Step 3:** In Caddy route section (lines 164-169), add branch for main domain:

```python
if sd.is_main_domain:
    await caddy.add_main_domain(settings.base_domain, port=port)
```

**Step 4:** Commit

```bash
git add src/pit_panel/web/routes/apps.py && git commit -m "feat: handle is_main_domain in app deploy"
```

### Task 4: Delete route — handle main domain

**Files:**
- Modify: `src/pit_panel/web/routes/apps.py:298-345`

**Step 1:** Before `docker_mgr.compose_down`, detect main domain and remove Caddy route:

```python
if sd.is_main_domain:
    try:
        caddy = CaddyManager(settings.caddy_admin_url)
        await caddy.remove_main_domain(settings.base_domain)
    except Exception:
        pass
```

**Step 2:** Commit

```bash
git add src/pit_panel/web/routes/apps.py && git commit -m "feat: handle is_main_domain in app delete"
```

### Task 5: Subdomains routes — exclude `_main_`

**Files:**
- Modify: `src/pit_panel/web/routes/subdomains.py`

**Step 1:** Add filter to exclude `is_main_domain=True` in all select queries.

Find all `select(Subdomain)` queries and add `.where(Subdomain.is_main_domain == False)`.

**Step 2:** Commit

```bash
git add src/pit_panel/web/routes/subdomains.py && git commit -m "fix: exclude _main_ subdomain from subdomain list"
```

### Task 6: Template — deploy form checkbox

**Files:**
- Modify: `src/pit_panel/web/templates/apps.html`

**Step 1:** Add checkbox in the deploy form, after the subdomain select:

```html
<div class="form-control">
  <label class="label cursor-pointer">
    <span class="label-text">Deploy on main domain ({{ settings.base_domain }})</span>
    <input type="checkbox" name="is_main_domain" class="checkbox checkbox-primary" />
  </label>
</div>
```

**Step 2:** Add JS to hide subdomain fields when checked:

```html
<script>
document.querySelector('input[name="is_main_domain"]').addEventListener('change', function() {
  document.querySelectorAll('.subdomain-fields').forEach(el => el.style.display = this.checked ? 'none' : '');
});
</script>
```

**Step 3:** In the app list, add badge for main domain:

```html
{% if sd.is_main_domain %}
  <span class="badge badge-accent">Main Domain</span>
{% endif %}
```

**Step 4:** Show URL as `{base_domain}` instead of `{subdomain}.{base_domain}`:

```html
{% if sd.is_main_domain %}
  <code>{{ settings.base_domain }}</code>
{% else %}
  <code>{{ sd.subdomain }}.{{ sd.base_domain }}</code>
{% endif %}
```

**Step 5:** Commit

```bash
git add src/pit_panel/web/templates/apps.html && git commit -m "feat: main domain checkbox in deploy form + badge"
```

### Task 7: Template — app detail badge

**Files:**
- Modify: `src/pit_panel/web/templates/app_detail.html`

**Step 1:** Show URL as `{base_domain}` when `sd.is_main_domain`:

```html
{% if sd.is_main_domain %}
  <p class="text-lg font-mono">{{ sd.base_domain }}</p>
{% else %}
  <p class="text-lg font-mono">{{ sd.subdomain }}.{{ sd.base_domain }}</p>
{% endif %}
```

**Step 2:** Add badge next to app name:

```html
{% if sd.is_main_domain %}
  <span class="badge badge-accent">Main Domain</span>
{% endif %}
```

**Step 3:** Commit

```bash
git add src/pit_panel/web/templates/app_detail.html && git commit -m "feat: main domain display in app detail"
```

### Task 8: Tests

**Files:**
- Create: `tests/unit/routes/test_main_domain.py`

**Step 1:** Write test for main domain deploy:

```python
"""Tests for main domain app deployment."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_main_domain_deploy_creates_subdomain(client, monkeypatch, settings):
    from pit_panel.db.models import Subdomain

    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: settings)

    async def mock_get_user(*args, **kwargs):
        from pit_panel.db.models import User
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    mock_compose_up = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(
        "pit_panel.core.docker_ops.DockerManager.compose_up", mock_compose_up
    )

    mock_add_main = AsyncMock(return_value={})
    monkeypatch.setattr(
        "pit_panel.core.caddy.CaddyManager.add_main_domain", mock_add_main
    )

    resp = client.post("/apps/deploy", data={
        "is_main_domain": "true",
        "stack_type": "static-nginx",
        "port": 8082,
    }, follow_redirects=False)

    assert resp.status_code == 302
    mock_compose_up.assert_called_once_with("_main_")
    mock_add_main.assert_called_once()


@pytest.mark.asyncio
async def test_main_domain_twice_rejected(client, monkeypatch, settings):
    monkeypatch.setattr("pit_panel.web.routes.apps.get_settings", lambda: settings)

    async def mock_get_user(*args, **kwargs):
        from pit_panel.db.models import User
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.apps.get_user", mock_get_user)

    class MockSD:
        id = 1
        subdomain = "_main_"
        base_domain = settings.base_domain
        is_main_domain = True
        app_type = "static-nginx"

    result_mock = AsyncMock()
    result_mock.scalar_one_or_none.return_value = MockSD()

    with patch("pit_panel.web.routes.apps.select"):
        with patch("pit_panel.web.routes.apps.db.execute", return_value=result_mock):
            resp = client.post("/apps/deploy", data={
                "is_main_domain": "true",
                "stack_type": "static-nginx",
                "port": 8082,
            })

    assert resp.status_code == 200
    assert "Main domain app already deployed" in resp.text
```

**Step 2:** Run tests

```bash
uv run pytest -q tests/unit/routes/test_main_domain.py -v
```

**Step 3:** Commit

```bash
git add tests/unit/routes/test_main_domain.py && git commit -m "test: main domain deploy/duplicate rejection"
```

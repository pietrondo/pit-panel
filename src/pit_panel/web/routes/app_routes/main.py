"""App routes: list, analyze repo, detail, update all."""

import asyncio
import contextlib
import logging
import os
import re

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.app_manager import AppManager
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.docker_ops import DockerManager
from pit_panel.core.repo_detector import analyze_repo
from pit_panel.db.models import Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

from .router import router

logger = logging.getLogger(__name__)


def _get_db_password(settings, subdomain: str) -> str | None:
    env_path = os.path.join(settings.apps_dir, subdomain, ".env")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("WORDPRESS_DB_PASSWORD=") or line.startswith("DB_PASSWORD="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Failed to read db password from {env_path}: {e}")
    return None


def _has_db_container(settings, subdomain: str) -> bool:
    compose_path = os.path.join(settings.apps_dir, subdomain, "docker-compose.yml")
    try:
        with open(compose_path) as f:
            content = f.read().lower()
        return "mysql" in content or "mariadb" in content or "postgres" in content
    except Exception as e:
        logger.warning(f"Failed to read docker-compose for {subdomain}: {e}")
        return False


@router.get("/apps", response_class=HTMLResponse)
async def apps_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")
            response.headers["HX-Redirect"] = "/login"
            return response
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
    subdomains = result.scalars().all()
    mgr = AppManager()
    templates = mgr.list_templates()
    template_infos = [{"name": t, "meta": mgr.get_template_info(t)} for t in templates]

    return render(
        "apps.html",
        user=user,
        settings=settings,
        subdomains=subdomains,
        templates=templates,
        template_infos=template_infos,
        error=None,
        detected=None,
    )


@router.post("/apps/analyze-repo", response_class=HTMLResponse)
async def app_analyze_repo(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return HTMLResponse("")

    form = await request.form()
    repo_url = str(form.get("repo_url", "")).strip()
    if not repo_url:
        return HTMLResponse('<p class="text-red-500 text-sm">Inserisci un URL GitHub</p>')

    try:
        detected = await analyze_repo(repo_url)
    except ValueError as e:
        return HTMLResponse(f'<p class="text-red-500 text-sm">{e}</p>')
    except Exception as e:
        logger.exception(f"Repo analysis failed for {repo_url}")
        return HTMLResponse(f'<p class="text-red-500 text-sm">Errore: {e}</p>')

    settings = get_settings()
    mgr = AppManager(settings.apps_dir)
    templates = mgr.list_templates()
    template_infos = {t: mgr.get_template_info(t) for t in templates}

    meta = template_infos.get(detected.stack_type, {})
    display = meta.get("display_name", detected.display_name)
    icon = meta.get("icon", "📦")
    port = meta.get("default_port", 8000)

    confidence_pct = detected.confidence
    badge_color = (
        "badge-green"
        if confidence_pct >= 90
        else "badge-yellow"
        if confidence_pct >= 50
        else "badge-red"
    )
    pct_label = "Deploy automatico" if confidence_pct >= 90 else "Deploy manuale"

    indicators_html = " ".join(
        f'<code class="text-xs bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">{i}</code>'
        for i in detected.indicators
    )

    result = await db.execute(
        select(Subdomain).where(Subdomain.app_type.is_(None)).order_by(Subdomain.created_at.asc())
    )
    available_sds = result.scalars().all()
    name_from_repo = repo_url.rstrip("/").split("/")[-1]
    name_from_repo = re.sub(r"[^a-z0-9-]", "", name_from_repo.lower().replace("_", "-"))[:40]

    sd_options = ""
    for sd in available_sds:
        sd_options += f'<option value="{sd.id}">{sd.subdomain}.{sd.base_domain}</option>'

    div_cls = (
        "p-4 rounded-lg border border-green-200 dark:border-green-800"
        " bg-green-50 dark:bg-green-900/20"
    )
    return HTMLResponse(f'''
<div class="{div_cls}">
    <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
            <span class="text-2xl">{icon}</span>
            <div>
                <span class="font-semibold text-gray-900 dark:text-white">{display}</span>
                <span class="badge {badge_color} ml-2">{confidence_pct}%</span>
            </div>
        </div>
        <span class="text-xs text-gray-500">{detected.stack_type}</span>
    </div>
    <div class="flex flex-wrap gap-1 mb-3">{indicators_html}</div>
    <form method="POST" action="/apps/deploy-from-repo" class="space-y-3"
          hx-post="/apps/deploy-from-repo"
          hx-target="#repo-result"
          hx-swap="innerHTML">
        <input type="hidden" name="repo_url" value="{repo_url}">
        <input type="hidden" name="stack_type" value="{detected.stack_type}">
        <input type="hidden" name="port" value="{port}">
        <label class="flex items-center gap-2 text-sm">
            <input type="checkbox" name="is_main_domain" value="true">
            <span>Deploy on main domain <code>{settings.base_domain or '—'}</code></span>
        </label>
        <div class="flex gap-2">
            <select name="subdomain_id" class="input text-sm">
                <option value="-1">New: {name_from_repo}.{settings.base_domain}</option>
                {sd_options}
            </select>
            <input type="text" name="new_subdomain" class="input text-sm w-32"
                   placeholder="or custom name">
        </div>
        <div class="flex items-center gap-3">
            <button type="submit" class="btn-ghost text-indigo-700 dark:text-indigo-400 text-sm"
                    hx-indicator="#deploy-indicator">
                🚀 Deploy
            </button>
            <span id="deploy-indicator" class="htmx-indicator">
                <span class="inline-block w-4 h-4 border-2 border-indigo-500
                             border-t-transparent rounded-full animate-spin"></span>
            </span>
            <span class="text-xs text-gray-500">{pct_label}</span>
        </div>
    </form>
</div>
''')


@router.get("/apps/{sd_id}", response_class=HTMLResponse)
async def app_detail(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")
            response.headers["HX-Redirect"] = "/login"
            return response
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return RedirectResponse("/apps", status_code=302)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    containers = []
    with contextlib.suppress(Exception):
        containers = await docker_mgr.compose_ps(sd.subdomain)

    logs = ""
    try:
        logs = await docker_mgr.compose_logs(sd.subdomain, tail=50)
    except Exception as e:
        logger.error(f"Failed to fetch logs for {sd.subdomain}: {e}")
        logs = "Error fetching logs"

    mgr = AppManager()
    app_info = mgr.get_template_info(sd.app_type) if sd.app_type else {}

    # SSL cert status
    ssl_info: dict[str, object] = {"has_cert": False, "expires_in_days": None, "issuer": None}
    base_domain = sd.base_domain or settings.base_domain
    if base_domain and sd.subdomain:
        caddy = CaddyManager(settings.caddy_admin_url)
        fqdn = base_domain if sd.is_main_domain else f"{sd.subdomain}.{base_domain}"

        ca_domains: list[str] = []
        with contextlib.suppress(Exception):
            ca_domains = await caddy._get_managed_domains()

        if fqdn in ca_domains:
            certs: list[dict[str, object]] = []
            with contextlib.suppress(Exception):
                certs = await caddy.get_certificates()

            for c in certs:
                if c.get("domains", "").startswith(fqdn):
                    ssl_info = {
                        "has_cert": True,
                        "expires_in_days": c.get("expires_in_days"),
                        "issuer": c.get("issuer"),
                        "not_after": c.get("not_after", ""),
                    }
                    break
            else:
                ssl_info = {
                    "has_cert": True,
                    "expires_in_days": None,
                    "issuer": "Pending...",
                    "not_after": "",
                }

    needs_db = sd.app_type in ("wordpress", "ghost")
    db_password = _get_db_password(settings, sd.subdomain) if needs_db else None
    has_db = _has_db_container(settings, sd.subdomain)

    return render(
        "app_detail.html",
        user=user,
        sd=sd,
        containers=containers,
        logs=logs,
        app_info=app_info,
        db_password=db_password,
        db_container=has_db,
        app_version=app_info.get("version", ""),
        app_port=app_info.get("default_port", ""),
        ssl_info=ssl_info,
    )


@router.post("/apps/update-all", response_class=HTMLResponse)
async def app_update_all(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")
            response.headers["HX-Redirect"] = "/login"
            return response
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)
    result = await db.execute(select(Subdomain).where(Subdomain.app_type.isnot(None)))
    apps = result.scalars().all()

    # Limit concurrency to 3 simultaneous docker operations to avoid resource exhaustion
    semaphore = asyncio.Semaphore(3)

    async def _update_app(sd: Subdomain) -> tuple[str, bool]:
        async with semaphore:
            try:
                r = await docker_mgr.run_compose_command(sd.subdomain, ["pull"])
                pull_ok = r.get("success", False)
                if pull_ok:
                    await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
                return (sd.subdomain, pull_ok)
            except Exception as e:
                logger.error(f"Update all failed for {sd.subdomain}: {e}")
                return (sd.subdomain, False)

    results = await asyncio.gather(*[_update_app(sd) for sd in apps])

    ok_count = sum(1 for _, ok in results if ok)
    total = len(results)
    html = (
        '<div class="p-3 rounded-lg bg-green-50 dark:bg-green-900/20'
        ' border border-green-200 dark:border-green-800">'
        f'<p class="text-sm text-green-700 dark:text-green-400">'
        f"Updated {ok_count}/{total} apps</p></div>"
    )
    return HTMLResponse(html)

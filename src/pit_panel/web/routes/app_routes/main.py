"""App deployment main routes: list, analyze, deploy, detail."""

import asyncio
import contextlib
import datetime
import logging
import os
import re
from pathlib import Path

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.app_manager import AppManager
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.docker_ops import DockerManager
from pit_panel.core.repo_detector import analyze_repo
from pit_panel.db.models import AppDeployment, AuditLog, Subdomain
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
    auto = confidence_pct >= 90
    pct_label = "Confidenza alta -> deploy automatico" if auto else "Confidenza bassa"

    indicators_html = " ".join(
        f'<code class="text-xs bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">{i}</code>'
        for i in detected.indicators
    )

    div_cls = "p-4 rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20"  # noqa: E501
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
    <div class="flex items-center gap-3">
        <form method="POST" action="/apps/deploy-from-repo" class="inline">
            <input type="hidden" name="repo_url" value="{repo_url}">
            <input type="hidden" name="stack_type" value="{detected.stack_type}">
            <input type="hidden" name="port" value="{port}">
            <button type="submit" class="btn-ghost text-indigo-700 dark:text-indigo-400 text-sm"
                    {"hx-disable" if auto else ""}>
                {"🚀 Deploy Automatico" if auto else "Deploy Manuale"}
            </button>
        </form>
        <p class="text-xs text-gray-500">{pct_label}</p>
    </div>
</div>
''')


@router.post("/apps/deploy", response_class=HTMLResponse)
async def app_deploy(
    request: Request,
    subdomain_id: int = Form(-1),
    new_subdomain: str = Form(""),
    stack_type: str = Form(...),
    port: int = Form(8000),
    is_main_domain: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    mgr = AppManager(settings.apps_dir)
    docker_mgr = DockerManager(settings.apps_dir)

    sd = None
    error = None

    # Resolve subdomain: use existing by ID or create new
    if is_main_domain:
        if not settings.base_domain:
            error = "Base domain not configured. Set it in Settings."
        else:
            existing = await db.execute(
                select(Subdomain).where(
                    Subdomain.is_main_domain,
                    Subdomain.base_domain == settings.base_domain,
                )
            )
            sd = existing.scalar_one_or_none()
            if sd:
                if sd.app_type:
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
    elif subdomain_id > 0:
        result = await db.execute(select(Subdomain).where(Subdomain.id == subdomain_id))
        sd = result.scalar_one_or_none()
        if not sd:
            error = "Subdomain not found"
    elif new_subdomain.strip():
        name = new_subdomain.strip().lower().replace(" ", "-")
        if not re.fullmatch(r"^[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$", name):
            error = f"Invalid subdomain name: {name}"
        else:
            if not settings.base_domain:
                error = "Base domain not configured. Set it in Settings."
            else:
                existing = await db.execute(
                    select(Subdomain).where(
                        Subdomain.subdomain == name,
                        Subdomain.base_domain == settings.base_domain,
                    )
                )
                sd = existing.scalar_one_or_none()
                if not sd:
                    sd = Subdomain(
                        subdomain=name,
                        base_domain=settings.base_domain,
                        owner_user_id=user.id,
                    )
                    db.add(sd)
                    await db.flush()
    else:
        error = "Select an existing subdomain or enter a new name"

    if error or not sd:
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        templates = mgr.list_templates()
        template_infos = [{"name": t, "meta": mgr.get_template_info(t)} for t in templates]
        return render(
            "apps.html",
            user=user,
            settings=settings,
            subdomains=subdomains,
            templates=templates,
            template_infos=template_infos,
            error=error,
            detected=None,
        )

    # Deploy template
    try:
        mgr.deploy_template(sd.subdomain, stack_type, variables={"PORT": str(port)})
    except ValueError as e:
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        tpls = mgr.list_templates()
        infos = [{"name": t, "meta": mgr.get_template_info(t)} for t in tpls]
        return render(
            "apps.html",
            user=user,
            settings=settings,
            subdomains=subdomains,
            templates=tpls,
            template_infos=infos,
            error=str(e),
            detected=None,
        )

    # Docker compose up
    compose_ok = False
    compose_logs = ""
    try:
        result = await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
        compose_ok = result.get("success", False)
        compose_logs = (result.get("stdout", "") + result.get("stderr", ""))[:500]
        if not compose_ok:
            error = f"Docker compose failed: {result.get('stderr', '')[:300]}"
    except Exception as e:
        error = f"Docker compose error: {e}"

    # Auto-setup WordPress
    if compose_ok and stack_type == "wordpress" and settings.base_domain:
        fqdn = f"{sd.subdomain}.{settings.base_domain}"
        try:
            env_path = Path(settings.apps_dir) / sd.subdomain / ".env"
            env_vars = {}
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
            import shlex

            wp_title = shlex.quote(env_vars.get("WP_TITLE", "My Blog"))
            wp_user = shlex.quote(env_vars.get("WP_ADMIN_USER", "admin"))
            wp_pass = shlex.quote(env_vars.get("WP_ADMIN_PASSWORD", "admin"))
            wp_email = shlex.quote(env_vars.get("WP_ADMIN_EMAIL", "admin@localhost"))
            wp_locale = shlex.quote(env_vars.get("WP_LOCALE", "it_IT"))
            fqdn_q = shlex.quote(f"https://{fqdn}")
            await asyncio.sleep(8)
            await docker_mgr.exec_command(
                sd.subdomain,
                "wordpress",
                [
                    "sh",
                    "-c",
                    f"curl -sSL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar"
                    f" -o /tmp/wp-cli.phar"
                    f" && php /tmp/wp-cli.phar core install"
                    f" --url={fqdn_q}"
                    f" --title={wp_title}"
                    f" --admin_user={wp_user}"
                    f" --admin_password={wp_pass}"
                    f" --admin_email={wp_email}"
                    f" --locale={wp_locale}"
                    f" --skip-email"
                    f" && rm /tmp/wp-cli.phar",
                ],
            )
        except Exception as e:
            logger.warning(f"WordPress auto-setup failed: {e}")

    # Caddy route
    if settings.base_domain:
        try:
            caddy = CaddyManager(settings.caddy_admin_url)
            if sd.is_main_domain:
                await caddy.add_main_domain(settings.base_domain, port=port)
            elif sd.app_type != stack_type:
                await caddy.add_subdomain(sd.subdomain, settings.base_domain, port=port)
                fqdn = f"{sd.subdomain}.{settings.base_domain}"
                await caddy.renew_certificate(fqdn)
        except Exception as e:
            logger.error(f"Caddy route error for {sd.subdomain}: {e}")
            error = (error or "") + f" | Caddy route error: {e}"

    sd.app_type = stack_type
    sd.last_deployed = datetime.datetime.now(datetime.UTC)

    deployment = AppDeployment(
        subdomain_id=sd.id,
        stack_type=stack_type,
        compose_path=f"{settings.apps_dir}/{sd.subdomain}/docker-compose.yml",
        status="running" if compose_ok else "failed",
    )
    db.add(deployment)

    db.add(
        AuditLog(
            user_id=user.id,
            action="app_deploy",
            target_type="subdomain",
            target_id=sd.id,
            details={"stack": stack_type, "subdomain": sd.subdomain, "success": compose_ok},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    if compose_ok:
        from pit_panel.core.notifier import notify_app_deploy

        base_domain = sd.base_domain or settings.base_domain
        await notify_app_deploy(sd.subdomain, stack_type, f"{sd.subdomain}.{base_domain}")

    logs_escaped = (compose_logs or "").replace("&", "&amp;").replace("<", "&lt;")
    logs_escaped = logs_escaped.replace(">", "&gt;").replace("\n", "<br>")
    pre_style = 'class="text-xs bg-gray-950 p-3 rounded overflow-auto max-h-60"'
    if error:
        return HTMLResponse(
            '<div class="card p-6 border-red-400 dark:border-red-700">'
            '<h3 class="text-red-600 font-semibold mb-2">Deploy failed</h3>'
            f'<p class="text-sm text-red-500 mb-3">{error}</p>'
            f'<pre {pre_style} style="color:#fca5a5">{logs_escaped}</pre>'
            "</div>"
        )
    fqdn = f"{sd.subdomain}.{sd.base_domain or settings.base_domain}"
    return HTMLResponse(
        '<div class="card p-6 border-green-400 dark:border-green-700">'
        '<h3 class="text-green-600 font-semibold mb-2">Deploy successful!</h3>'
        f'<p class="text-sm mb-1"><a href="/apps/{sd.id}" class="text-indigo-600 underline">'
        "Open app details &rarr;</a></p>"
        f'<p class="text-xs text-gray-500 mb-3">{fqdn}</p>'
        f'<pre {pre_style} style="color:#86efac">{logs_escaped}</pre>'
        "</div>"
    )


@router.post("/apps/deploy-from-repo", response_class=HTMLResponse)
async def app_deploy_from_repo(
    request: Request,
    repo_url: str = Form(...),
    stack_type: str = Form(...),
    port: int = Form(8000),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    if not settings.base_domain:
        return HTMLResponse('<p class="text-red-500">Base domain not configured</p>')

    name = repo_url.rstrip("/").split("/")[-1]
    name = re.sub(r"[^a-z0-9-]", "", name.lower().replace("_", "-"))[:40]
    if not name:
        name = "app"

    existing = await db.execute(
        select(Subdomain).where(
            Subdomain.subdomain == name,
            Subdomain.base_domain == settings.base_domain,
        )
    )
    sd = existing.scalar_one_or_none()
    if sd:
        name = f"{name}-{os.urandom(2).hex()}"
        sd = None

    if not sd:
        sd = Subdomain(
            subdomain=name,
            base_domain=settings.base_domain,
            owner_user_id=user.id,
        )
        db.add(sd)
        await db.flush()

    mgr = AppManager(settings.apps_dir)
    docker_mgr = DockerManager(settings.apps_dir)

    try:
        mgr.deploy_template(sd.subdomain, stack_type, variables={"PORT": str(port)})
    except ValueError as e:
        return HTMLResponse(f'<p class="text-red-500">{e}</p>')

    try:
        result = await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
        compose_ok = result.get("success", False)
    except Exception:
        compose_ok = False

    if settings.base_domain:
        try:
            caddy = CaddyManager(settings.caddy_admin_url)
            await caddy.add_subdomain(sd.subdomain, settings.base_domain, port=port)
            fqdn = f"{sd.subdomain}.{settings.base_domain}"
            await caddy.renew_certificate(fqdn)
        except Exception as e:
            logger.error(f"Caddy route error for {sd.subdomain}: {e}")

    sd.app_type = stack_type
    sd.last_deployed = datetime.datetime.now(datetime.UTC)

    db.add(
        AppDeployment(
            subdomain_id=sd.id,
            stack_type=stack_type,
            compose_path=f"{settings.apps_dir}/{sd.subdomain}/docker-compose.yml",
            status="running" if compose_ok else "failed",
        )
    )
    db.add(
        AuditLog(
            user_id=user.id,
            action="app_deploy",
            target_type="subdomain",
            target_id=sd.id,
            details={
                "stack": stack_type,
                "repo": repo_url,
                "subdomain": sd.subdomain,
                "success": compose_ok,
            },
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    return RedirectResponse(f"/apps/{sd.id}", status_code=302)


@router.get("/apps/{sd_id}", response_class=HTMLResponse)
async def app_detail(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
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
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

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
    return HTMLResponse(html, headers={"HX-Refresh": "true"})

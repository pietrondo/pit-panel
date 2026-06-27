"""App deployment wizard routes."""

import asyncio
import contextlib
import datetime
import logging
import os
import re

from fastapi import APIRouter, Depends, Form, Request
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

router = APIRouter()

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
        "badge-green" if confidence_pct >= 90
        else "badge-yellow" if confidence_pct >= 50
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
                    {'hx-disable' if auto else ''}>
                {'🚀 Deploy Automatico' if auto else 'Deploy Manuale'}
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
        if not re.fullmatch(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", name):
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
        mgr2 = AppManager()
        templates = mgr2.list_templates()
        template_infos = [{"name": t, "meta": mgr2.get_template_info(t)} for t in templates]
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
        mgr2 = AppManager()
        tpls = mgr2.list_templates()
        infos = [{"name": t, "meta": mgr2.get_template_info(t)} for t in tpls]
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
    try:
        result = await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
        compose_ok = result.get("success", False)
        if not compose_ok:
            error = f"Docker compose failed: {result.get('stderr', '')[:300]}"
    except Exception as e:
        error = f"Docker compose error: {e}"

    # Caddy route
    if settings.base_domain:
        try:
            caddy = CaddyManager(settings.caddy_admin_url)
            if sd.is_main_domain:
                await caddy.add_main_domain(settings.base_domain, port=port)
            elif sd.app_type != stack_type:
                await caddy.add_subdomain(sd.subdomain, settings.base_domain)
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

    if error:
        result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
        subdomains = result.scalars().all()
        mgr2 = AppManager()
        templates = mgr2.list_templates()
        template_infos = [{"name": t, "meta": mgr2.get_template_info(t)} for t in templates]
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

    return RedirectResponse(f"/apps/{sd.id}", status_code=302)


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
            await caddy.add_subdomain(sd.subdomain, settings.base_domain)
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
            details={"stack": stack_type, "repo": repo_url,
                     "subdomain": sd.subdomain, "success": compose_ok},
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
    )


@router.post("/apps/{sd_id}/restart", response_class=HTMLResponse)
async def app_restart(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.run_compose_command(sd.subdomain, ["restart"])
    return RedirectResponse(f"/apps/{sd_id}", status_code=302)


@router.post("/apps/{sd_id}/stop", response_class=HTMLResponse)
async def app_stop(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.run_compose_command(sd.subdomain, ["down"])
        db.add(
            AuditLog(
                user_id=user.id,
                action="app_stop",
                target_type="subdomain",
                target_id=sd.id,
                details={"subdomain": sd.subdomain},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
    return RedirectResponse("/apps", status_code=302)


@router.post("/apps/{sd_id}/delete", response_class=HTMLResponse)
async def app_delete(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if sd:
        settings = get_settings()

        # 1. Stop containers and remove volumes
        docker_mgr = DockerManager(settings.apps_dir)
        await docker_mgr.run_compose_command(sd.subdomain, ["down", "-v"])

        # 2. Delete Caddy route
        if settings.base_domain and sd.app_type:
            try:
                caddy = CaddyManager(settings.caddy_admin_url)
                if sd.is_main_domain:
                    await caddy.remove_main_domain(settings.base_domain)
                else:
                    await caddy.remove_subdomain(sd.subdomain, settings.base_domain)
            except Exception as e:
                logger.warning(f"Failed to remove Caddy route for {sd.subdomain}: {e}")

        # 3. Delete app files
        mgr = AppManager(settings.apps_dir)
        mgr.delete_app(sd.subdomain)

        # 4. Reset subdomain app_type
        old_app_type = sd.app_type
        sd.app_type = None

        # 5. Delete AppDeployment DB records
        await db.execute(
            AppDeployment.__table__.delete().where(AppDeployment.subdomain_id == sd.id)
        )

        db.add(
            AuditLog(
                user_id=user.id,
                action="app_delete",
                target_type="subdomain",
                target_id=sd.id,
                details={"subdomain": sd.subdomain, "app_type": old_app_type},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
    return RedirectResponse("/apps", status_code=302)


@router.get("/apps/{sd_id}/containers", response_class=HTMLResponse)
async def app_containers_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    containers = []
    with contextlib.suppress(Exception):
        containers = await docker_mgr.compose_ps(sd.subdomain)

    return render("tabs/_containers.html", request=request, sd=sd, containers=containers)


@router.get("/apps/{sd_id}/backup", response_class=HTMLResponse)
async def app_backup_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    return render("tabs/_backup.html", request=request, sd=sd)


@router.get("/apps/{sd_id}/logs", response_class=HTMLResponse)
async def app_logs_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<div class='text-red-500'>App not found</div>")

    settings = get_settings()
    docker_mgr = DockerManager(settings.apps_dir)

    logs = ""
    try:
        logs = await docker_mgr.compose_logs(sd.subdomain, tail=50)
    except Exception:
        logs = "Error fetching logs"

    return render("tabs/_logs.html", request=request, sd=sd, logs=logs)


@router.get("/apps/{sd_id}/env", response_class=HTMLResponse)
async def app_env_get(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return "<div class='text-red-500'>App not found</div>"

    settings = get_settings()
    env_path = os.path.join(settings.apps_dir, sd.subdomain, ".env")
    env_content = ""
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                env_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read .env file at {env_path}: {e}")
            env_content = "# Error reading .env file"
    else:
        env_content = "# No .env file found"

    return render(
        "tabs/_env.html", request=request, sd=sd, env_content=env_content, error=None, success=None
    )


@router.post("/apps/{sd_id}/env", response_class=HTMLResponse)
async def app_env_post(
    request: Request, sd_id: int, env_content: str = Form(...), db: AsyncSession = Depends(get_db)
):
    user = await get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return "<div class='text-red-500'>App not found</div>"

    settings = get_settings()
    env_path = os.path.join(settings.apps_dir, sd.subdomain, ".env")

    if any(c in env_content for c in ['"', "'"]):
        return HTMLResponse("Quotes are not allowed to prevent quote evasion.", status_code=400)

    error = None
    success = None
    try:
        with open(env_path, "w") as f:
            # Basic sanitization
            safe_content = env_content.replace("\r", "")
            f.write(safe_content)
        success = (
            "Environment variables updated successfully. "
            "You may need to restart the app for changes to take effect."
        )

        db.add(
            AuditLog(
                user_id=user.id,
                action="app_env_update",
                target_type="subdomain",
                target_id=sd.id,
                details={"subdomain": sd.subdomain},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to save .env file for {sd.subdomain}: {e}")
        error = f"Error saving .env file: {e}"

    return render(
        "tabs/_env.html",
        request=request,
        sd=sd,
        env_content=env_content,
        error=error,
        success=success,
    )


@router.post("/apps/{sd_id}/wp/flush-cache", response_class=HTMLResponse)
async def app_wp_flush_cache(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<span class='text-red-500 text-xs'>App not found</span>")


    settings = get_settings()

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "exec",
            "-T",
            "wordpress",
            "wp",
            "cache",
            "flush",
            "--allow-root",
            cwd=os.path.join(settings.apps_dir, sd.subdomain),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode()
            return HTMLResponse(f"<span class='text-red-500 text-xs'>Error: {err}</span>")
    except Exception as e:
        err = str(e)
        return HTMLResponse(f"<span class='text-red-500 text-xs'>Exception: {err}</span>")

    return HTMLResponse(
        "<span class='text-green-600 text-sm font-medium p-2 bg-green-50 rounded dark:bg-green-900/30 dark:text-green-400'>Cache flushed successfully!</span>"
    )


@router.post("/apps/{sd_id}/wp/update-plugins", response_class=HTMLResponse)
async def app_wp_update_plugins(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<span class='text-red-500 text-xs'>App not found</span>")


    settings = get_settings()

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "exec",
            "-T",
            "wordpress",
            "wp",
            "plugin",
            "update",
            "--all",
            "--allow-root",
            cwd=os.path.join(settings.apps_dir, sd.subdomain),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode()
            return HTMLResponse(f"<span class='text-red-500 text-xs'>Error: {err}</span>")
    except Exception as e:
        err = str(e)
        return HTMLResponse(f"<span class='text-red-500 text-xs'>Exception: {err}</span>")

    return HTMLResponse(
        "<span class='text-green-600 text-sm font-medium p-2 bg-green-50 rounded dark:bg-green-900/30 dark:text-green-400'>Plugins updated successfully!</span>"
    )


@router.post("/apps/{sd_id}/wp/update-core", response_class=HTMLResponse)
async def app_wp_update_core(request: Request, sd_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)
    if not user:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/login"
        return response

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd:
        return HTMLResponse("<span class='text-red-500 text-xs'>App not found</span>")


    settings = get_settings()

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "exec",
            "-T",
            "wordpress",
            "wp",
            "core",
            "update",
            "--allow-root",
            cwd=os.path.join(settings.apps_dir, sd.subdomain),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode()
            return HTMLResponse(f"<span class='text-red-500 text-xs'>Error: {err}</span>")
    except Exception as e:
        err = str(e)
        return HTMLResponse(f"<span class='text-red-500 text-xs'>Exception: {err}</span>")

    return HTMLResponse(
        "<span class='text-green-600 text-sm font-medium p-2 bg-green-50 rounded dark:bg-green-900/30 dark:text-green-400'>Core updated successfully!</span>"
    )

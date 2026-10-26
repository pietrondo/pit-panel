"""App deployment routes: template deploy and deploy-from-repo."""

import asyncio
import contextlib
import datetime
import html
import logging
import os
import re
import shutil
from pathlib import Path

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.app_manager import AppManager
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.docker_ops import DockerManager
from pit_panel.core.dynu import DynuClient
from pit_panel.core.repo_validator import (
    isolated_git_env,
    redact_repository_url,
    validate_repository_url_async,
)
from pit_panel.db.models import AppDeployment, AuditLog, Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

from .router import router

logger = logging.getLogger(__name__)


def _effective_domain(settings) -> str:
    effective = getattr(settings, "effective_domain", None)
    if isinstance(effective, str) and effective:
        return effective
    return settings.base_domain


def _dynu_enabled(settings) -> bool:
    return all(
        isinstance(getattr(settings, key, ""), str) and getattr(settings, key, "").strip()
        for key in ("dynu_api_key", "dynu_domain")
    )


async def _provision_dynu(settings, name: str, domain: str) -> tuple[int, str] | None:
    if not _dynu_enabled(settings):
        return None
    ip = settings._detect_ip()
    async with DynuClient(settings.dynu_api_key) as client:
        record = await client.add_a_record(domain, name, ip)
    return int(record["id"]), ip


async def _allocate_host_port(
    db, requested_port: int, settings, current_subdomain_id: int | None = None
) -> int:
    port = int(requested_port)
    if not 8000 <= port <= 8999 or port == int(getattr(settings, "port", 8080)):
        raise ValueError("Port must be within the managed range and cannot use the panel port")
    # An app reserves two ports: the WordPress template also binds PORT+1 (phpMyAdmin).
    query = (
        select(Subdomain.id)
        .where(Subdomain.host_port.in_([port - 1, port, port + 1]))
        .limit(1)
    )
    if current_subdomain_id is not None:
        query = query.where(Subdomain.id != current_subdomain_id)
    result = await db.execute(query)
    if result.scalar_one_or_none() is not None:
        raise ValueError("Requested port is already reserved")
    return port


async def _cleanup_provisioned(settings, sd: Subdomain, db: AsyncSession) -> None:
    if getattr(sd, "_provisioned_dynu_record_id", None) and _dynu_enabled(settings):
        try:
            async with DynuClient(settings.dynu_api_key) as client:
                await client.delete_record(sd.base_domain, sd._provisioned_dynu_record_id)
        except Exception:
            logger.exception("Failed to clean up Dynu record for %s", sd.subdomain)
    if getattr(sd, "_caddy_route_created", False) and _effective_domain(settings):
        try:
            caddy = CaddyManager(settings.caddy_admin_url)
            if getattr(sd, "_caddy_route_kind", "subdomain") == "main":
                await caddy.remove_main_domain(sd.base_domain)
            else:
                await caddy.remove_subdomain(sd.subdomain, sd.base_domain)
        except Exception:
            logger.exception("Failed to clean up Caddy route for %s", sd.subdomain)
    docker_mgr = getattr(sd, "_deployment_docker_mgr", None)
    if getattr(sd, "_compose_started", False) and docker_mgr:
        with contextlib.suppress(Exception):
            await docker_mgr.run_compose_command(sd.subdomain, ["down"])
    if getattr(sd, "_app_dir_created", False):
        with contextlib.suppress(Exception):
            shutil.rmtree(Path(settings.apps_dir) / sd.subdomain)
    await db.rollback()


async def _stop_git_process(proc) -> None:
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
    try:
        await asyncio.wait_for(proc.communicate(), timeout=5)
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(proc.communicate(), timeout=5)

def _patch_vite_allowed_hosts(src_dir: Path, hostname: str = "localhost") -> None:
    for name in ("vite.config.ts", "vite.config.js", "vite.config.mjs"):
        cfg = src_dir / name
        if cfg.exists():
            wrapper = src_dir / "vite.config.pit.mjs"
            wrapper.write_text(
                "import { mergeConfig } from 'vite'\n"
                f"import userConfig from './{name}'\n"
                "export default mergeConfig(userConfig,"
                f" {{ server: {{ allowedHosts: ['{hostname}'] }} }})\n"
            )
            return


async def _resolve_subdomain(
    db: AsyncSession,
    user_id: int,
    settings,
    is_main_domain: bool,
    subdomain_id: int,
    new_subdomain: str,
    is_admin: bool = False,
):
    if settings is None:
        settings = get_settings()
    sd = None
    error = None

    if is_main_domain:
        if not is_admin:
            error = "Administrator privileges required"
        elif not _effective_domain(settings):
            error = "Base domain not configured. Set it in Settings."
        else:
            existing = await db.execute(
                select(Subdomain).where(
                    Subdomain.is_main_domain,
                    Subdomain.base_domain == _effective_domain(settings),
                )
            )
            sd = existing.scalar_one_or_none()
            if sd:
                if sd.app_type:
                    error = "Main domain app already deployed"
            else:
                sd = Subdomain(
                    subdomain="_main_",
                    base_domain=_effective_domain(settings),
                    owner_user_id=user_id,
                    is_main_domain=True,
                )
                db.add(sd)
                sd._created_by_request = True
                await db.flush()
    elif subdomain_id > 0:
        result = await db.execute(select(Subdomain).where(Subdomain.id == subdomain_id))
        sd = result.scalar_one_or_none()
        if not sd:
            error = "Subdomain not found"
        elif not is_admin and sd.owner_user_id != user_id:
            error = "You do not own this subdomain"
    elif new_subdomain.strip():
        name = new_subdomain.strip().lower().replace(" ", "-")
        if not re.fullmatch(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$", name):
            error = f"Invalid subdomain name: {name}"
        else:
            if not _effective_domain(settings):
                error = "Base domain not configured. Set it in Settings."
            else:
                existing = await db.execute(
                    select(Subdomain).where(
                        Subdomain.subdomain == name,
                        Subdomain.base_domain == _effective_domain(settings),
                    )
                )
                sd = existing.scalar_one_or_none()
                if not sd:
                    if _dynu_enabled(settings) and not is_admin:
                        return None, "Administrator privileges required"
                    sd = Subdomain(
                        subdomain=name,
                        base_domain=_effective_domain(settings),
                        owner_user_id=user_id,
                    )
                    db.add(sd)
                    sd._created_by_request = True
                    await db.flush()
                    record = await _provision_dynu(settings, name, _effective_domain(settings))
                    if record:
                        sd.dynu_record_id, sd.dynu_ipv4 = record
                        sd._provisioned_dynu_record_id = record[0]
                elif not is_admin and sd.owner_user_id != user_id:
                    error = "You do not own this subdomain"
    else:
        error = "Select an existing subdomain or enter a new name"

    return sd, error


async def _render_apps_error(user, settings, db: AsyncSession, error: str, request: Request = None):
    if request and "hx-request" in request.headers:
        import html

        safe_error = html.escape(str(error))
        return HTMLResponse(
            f"""<div class="mb-4 p-4 rounded-lg border text-sm bg-red-50 dark:bg-red-900/20 """
            f"""border-red-200 dark:border-red-800 text-red-700 dark:text-red-300">
                <p class="font-medium">Error</p>
                <p class="mt-1 font-mono text-xs whitespace-pre-wrap">{safe_error}</p>
            </div>"""
        )
    result = await db.execute(select(Subdomain).order_by(Subdomain.created_at.desc()))
    subdomains = result.scalars().all()
    if not bool(getattr(user, "is_admin", False)):
        subdomains = [sd for sd in subdomains if sd.owner_user_id == user.id]
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


async def _auto_setup_wordpress(settings, sd, docker_mgr):
    fqdn = f"{sd.subdomain}.{_effective_domain(settings)}"
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


async def _setup_caddy_route(
    settings, sd, port: int, error: str | None, stack_type: str, track_resource: bool = False
) -> str | None:
    try:
        caddy = CaddyManager(settings.caddy_admin_url)
        if sd.is_main_domain:
            await caddy.add_main_domain(_effective_domain(settings), port=port)
            if track_resource:
                sd._caddy_route_created = True
                sd._caddy_route_kind = "main"
        elif sd.app_type != stack_type:
            await caddy.add_subdomain(sd.subdomain, _effective_domain(settings), port=port)
            if track_resource:
                sd._caddy_route_created = True
            fqdn = f"{sd.subdomain}.{_effective_domain(settings)}"
            renewal = await caddy.renew_certificate(fqdn)
            if isinstance(renewal, dict) and renewal.get("success") is False:
                raise RuntimeError("Caddy certificate renewal failed")
    except Exception as e:
        logger.error(f"Caddy route error for {sd.subdomain}: {e}")
        error = (error or "") + f" | Caddy route error: {e}"
    return error


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
        if "hx-request" in request.headers:
            response = HTMLResponse("")
            response.headers["HX-Redirect"] = "/login"
            return response
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    mgr = AppManager(settings.apps_dir)
    docker_mgr = DockerManager(settings.apps_dir)

    # Resolve subdomain: use existing by ID or create new
    sd, error = await _resolve_subdomain(
        db,
        user.id,
        settings,
        is_main_domain,
        subdomain_id,
        new_subdomain,
        bool(getattr(user, "is_admin", False)),
    )

    if error or not sd:
        return await _render_apps_error(user, settings, db, error, request)
    try:
        if getattr(sd, "host_port", None) is not None and port == 8000:
            port = sd.host_port
        port = await _allocate_host_port(db, port, settings, sd.id)
    except ValueError as exc:
        if bool(getattr(sd, "_created_by_request", False)):
            await _cleanup_provisioned(settings, sd, db)
        return await _render_apps_error(user, settings, db, str(exc), request)
    created_subdomain = bool(getattr(sd, "_created_by_request", False))
    sd._deployment_docker_mgr = docker_mgr
    sd._app_dir_created = not (Path(settings.apps_dir) / sd.subdomain).exists()
    if hasattr(sd, "host_port") and sd.host_port != port:
        try:
            sd.host_port = port
            await db.flush()
        except IntegrityError:
            await db.rollback()
            if created_subdomain:
                await _cleanup_provisioned(settings, sd, db)
            return await _render_apps_error(
                user, settings, db, "Requested port is already reserved", request
            )

    # Deploy template
    try:
        mgr.deploy_template(sd.subdomain, stack_type, variables={"PORT": str(port)})
    except ValueError as e:
        if created_subdomain:
            await _cleanup_provisioned(settings, sd, db)
        return await _render_apps_error(user, settings, db, str(e), request)

    # Docker compose up
    compose_ok = False
    compose_logs = ""
    try:
        sd._compose_started = created_subdomain
        result = await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
        compose_ok = result.get("success", False)
        compose_logs = (result.get("stdout", "") + result.get("stderr", ""))[:500]
        if not compose_ok:
            error = f"Docker compose failed: {result.get('stderr', '')[:300]}"
    except Exception as e:
        error = f"Docker compose error: {e}"

    if not compose_ok and created_subdomain:
        await _cleanup_provisioned(settings, sd, db)
        return await _render_apps_error(user, settings, db, error, request)

    # Auto-setup WordPress
    if compose_ok and stack_type == "wordpress" and _effective_domain(settings):
        await _auto_setup_wordpress(settings, sd, docker_mgr)

    # Caddy route
    if _effective_domain(settings):
        error = await _setup_caddy_route(
            settings, sd, port, error, stack_type, created_subdomain
        )

    if error and created_subdomain:
        await _cleanup_provisioned(settings, sd, db)
        return await _render_apps_error(user, settings, db, error, request)

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
    try:
        await db.commit()
    except Exception:
        await _cleanup_provisioned(settings, sd, db)
        raise

    if compose_ok:
        from pit_panel.core.notifier import notify_app_deploy

        base_domain = sd.base_domain or _effective_domain(settings)
        await notify_app_deploy(sd.subdomain, stack_type, f"{sd.subdomain}.{base_domain}")

    logs_escaped = (compose_logs or "").replace("&", "&amp;").replace("<", "&lt;")
    logs_escaped = logs_escaped.replace(">", "&gt;").replace("\n", "<br>")
    pre_style = 'class="text-xs bg-gray-950 p-3 rounded overflow-auto max-h-60"'
    if error:
        safe_error = html.escape(str(error))
        return HTMLResponse(
            '<div class="card p-6 border-red-400 dark:border-red-700">'
            '<h3 class="text-red-600 font-semibold mb-2">Deploy failed</h3>'
            f'<p class="text-sm text-red-500 mb-3">{safe_error}</p>'
            f'<pre {pre_style} style="color:#fca5a5">{logs_escaped}</pre>'
            "</div>"
        )
    fqdn = f"{sd.subdomain}.{sd.base_domain or _effective_domain(settings)}"
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
    subdomain_id: int = Form(-1),
    new_subdomain: str = Form(""),
    is_main_domain: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)
    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")
            response.headers["HX-Redirect"] = "/login"
            return response
        return RedirectResponse("/login", status_code=302)

    settings = get_settings()
    if not _effective_domain(settings):
        return HTMLResponse('<p class="text-red-500">Base domain not configured</p>')

    # Validate repo_url to prevent command injection via git clone
    if not repo_url or repo_url.startswith("-") or "ext::" in repo_url:
        return HTMLResponse('<p class="text-red-500">Invalid repository URL</p>', status_code=400)

    if "://" not in repo_url and not repo_url.startswith("git@"):
        return HTMLResponse(
            '<p class="text-red-500">Invalid repository URL scheme</p>', status_code=400
        )

    if not await validate_repository_url_async(repo_url):
        return HTMLResponse(
            '<p class="text-red-500">Repository provider is not allowed</p>', status_code=400
        )

    sd: Subdomain | None = None
    safe_repo_url = redact_repository_url(repo_url)

    # Main domain: reuse the `_main_` subdomain, allowing redeploy of the same
    # stack from this repo (unlike /apps/deploy, which always creates a new app).
    if is_main_domain:
        existing_main = await db.execute(
            select(Subdomain).where(
                Subdomain.is_main_domain,
                Subdomain.base_domain == _effective_domain(settings),
            )
        )
        sd = existing_main.scalar_one_or_none()
        if sd and sd.app_type and sd.app_type != stack_type:
            return HTMLResponse('<p class="text-red-500">Main domain app already deployed</p>')
        if not bool(getattr(user, "is_admin", False)):
            return HTMLResponse(
                '<p class="text-red-500">Administrator privileges required</p>',
                status_code=403,
            )
        if not sd:
            sd, error = await _resolve_subdomain(
                db, user.id, settings, True, -1, "", bool(getattr(user, "is_admin", False))
            )
            if sd and not existing_main:
                sd._created_by_request = True
            if error or not sd:
                safe_error = html.escape(str(error or "Main domain unavailable"))
                return HTMLResponse(
                    f'<p class="text-red-500">{safe_error}</p>'
                )

    # Try resolving by existing subdomain ID first
    if not sd and subdomain_id > 0:
        result = await db.execute(select(Subdomain).where(Subdomain.id == subdomain_id))
        sd = result.scalar_one_or_none()
        if sd and not bool(getattr(user, "is_admin", False)) and sd.owner_user_id != user.id:
            return HTMLResponse('<p class="text-red-500">You do not own this subdomain</p>')
        if sd and sd.app_type:
            return HTMLResponse(
                f'<p class="text-red-500">{sd.subdomain} already has an app deployed</p>'
            )

    # If a custom name was provided, resolve/create it
    if not sd and new_subdomain.strip():
        sd, error = await _resolve_subdomain(
            db,
            user.id,
            settings,
            False,
            -1,
            new_subdomain.strip(),
            bool(getattr(user, "is_admin", False)),
        )
        if error:
            return HTMLResponse(f'<p class="text-red-500">{html.escape(str(error))}</p>')

    # Fallback: auto-generate from repo name
    if not sd:
        name = repo_url.rstrip("/").split("/")[-1]
        name = re.sub(r"[^a-z0-9-]", "", name.lower().replace("_", "-"))[:40]
        if not name:
            name = "app"

        existing = await db.execute(
            select(Subdomain).where(
                Subdomain.subdomain == name,
                Subdomain.base_domain == _effective_domain(settings),
            )
        )
        sd = existing.scalar_one_or_none()
        if sd:
            name = f"{name}-{os.urandom(2).hex()}"
            sd = None

        if not sd:
            if _dynu_enabled(settings) and not bool(getattr(user, "is_admin", False)):
                return HTMLResponse(
                    '<p class="text-red-500">Administrator privileges required</p>',
                    status_code=403,
                )
            sd = Subdomain(
                subdomain=name,
                base_domain=_effective_domain(settings),
                owner_user_id=user.id,
            )
            db.add(sd)
            sd._created_by_request = True
            await db.flush()
            record = await _provision_dynu(settings, name, _effective_domain(settings))
            if record:
                sd.dynu_record_id, sd.dynu_ipv4 = record
                sd._provisioned_dynu_record_id = record[0]

    try:
        if getattr(sd, "host_port", None) is not None and port == 8000:
            port = sd.host_port
        port = await _allocate_host_port(db, port, settings, sd.id)
    except ValueError as exc:
        if bool(getattr(sd, "_created_by_request", False)):
            await _cleanup_provisioned(settings, sd, db)
        return HTMLResponse(
            f'<p class="text-red-500">{html.escape(str(exc))}</p>', status_code=400
        )
    if hasattr(sd, "host_port") and sd.host_port != port:
        try:
            sd.host_port = port
            await db.flush()
        except IntegrityError:
            await db.rollback()
            if bool(getattr(sd, "_created_by_request", False)):
                await _cleanup_provisioned(settings, sd, db)
            return HTMLResponse(
                '<p class="text-red-500">Requested port is already reserved</p>',
                status_code=409,
            )
    mgr = AppManager(settings.apps_dir)
    docker_mgr = DockerManager(settings.apps_dir)
    sd._deployment_docker_mgr = docker_mgr
    sd._app_dir_created = not (Path(settings.apps_dir) / sd.subdomain).exists()

    try:
        mgr.deploy_template(sd.subdomain, stack_type, variables={"PORT": str(port)})
    except ValueError as e:
        if bool(getattr(sd, "_created_by_request", False)):
            await _cleanup_provisioned(settings, sd, db)
        return HTMLResponse(f'<p class="text-red-500">{html.escape(str(e))}</p>')

    _source_stacks = {
        "nodejs": "app",
        "nextjs": "app",
        "python-flask": "app",
        "python-fastapi": "app",
        "static-nginx": "html",
    }
    if stack_type in _source_stacks:
        src_dir = Path(settings.apps_dir) / sd.subdomain / _source_stacks[stack_type]
        try:
            if src_dir.exists():
                shutil.rmtree(src_dir)
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-c",
                "http.followRedirects=false",
                "clone",
                "--depth",
                "1",
                "--",
                repo_url,
                str(src_dir),
                env=isolated_git_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                logger.error(
                    "Git clone failed for %s: %s",
                    safe_repo_url,
                    stderr.decode(errors="replace")[:300],
                )
                if bool(getattr(sd, "_created_by_request", False)):
                    await _cleanup_provisioned(settings, sd, db)
                return HTMLResponse(
                    '<p class="text-red-500">Git clone failed.</p>', status_code=502
                )
            else:
                _patch_vite_allowed_hosts(src_dir, f"{sd.subdomain}.{_effective_domain(settings)}")
        except PermissionError:
            if bool(getattr(sd, "_created_by_request", False)):
                await _cleanup_provisioned(settings, sd, db)
                return HTMLResponse(
                    f'<p class="text-red-500">Permission denied on {html.escape(str(src_dir))}.'
                " Run: sudo rm -rf {src_dir}</p>"
            )
        except asyncio.CancelledError:
            await _stop_git_process(proc)
            raise
        except TimeoutError:
            await _stop_git_process(proc)
            if bool(getattr(sd, "_created_by_request", False)):
                await _cleanup_provisioned(settings, sd, db)
            return HTMLResponse('<p class="text-red-500">Git clone timed out. Try again.</p>')
        except Exception as e:
            logger.error("Git clone error for %s: %s", safe_repo_url, e)
            if bool(getattr(sd, "_created_by_request", False)):
                await _cleanup_provisioned(settings, sd, db)
            return HTMLResponse(
                f'<p class="text-red-500">Clone failed: {html.escape(str(e)[:200])}</p>'
            )

    try:
        sd._compose_started = bool(getattr(sd, "_created_by_request", False))
        result = await docker_mgr.run_compose_command(sd.subdomain, ["up", "-d"])
        compose_ok = result.get("success", False)
        compose_error = (result.get("stderr", "") + result.get("stdout", ""))[:300]
    except Exception as e:
        compose_ok = False
        compose_error = str(e)[:300]

    if not compose_ok and bool(getattr(sd, "_created_by_request", False)):
        await _cleanup_provisioned(settings, sd, db)
        err_esc = html.escape(compose_error)
        return HTMLResponse(
            '<p class="text-red-500">Docker compose failed</p>'
            f'<pre>{err_esc}</pre>', status_code=502
        )

    if _effective_domain(settings):
        try:
            caddy = CaddyManager(settings.caddy_admin_url)
            if sd.is_main_domain:
                await caddy.add_main_domain(_effective_domain(settings), port=port)
                if bool(getattr(sd, "_created_by_request", False)):
                    sd._caddy_route_created = True
                    sd._caddy_route_kind = "main"
            else:
                await caddy.add_subdomain(sd.subdomain, _effective_domain(settings), port=port)
                if bool(getattr(sd, "_created_by_request", False)):
                    sd._caddy_route_created = True
                    sd._caddy_route_kind = "subdomain"
                fqdn = f"{sd.subdomain}.{_effective_domain(settings)}"
                renewal = await caddy.renew_certificate(fqdn)
                if isinstance(renewal, dict) and renewal.get("success") is False:
                    raise RuntimeError("Caddy certificate renewal failed")
        except Exception as e:
            logger.error(f"Caddy route error for {sd.subdomain}: {e}")
            if bool(getattr(sd, "_created_by_request", False)):
                await _cleanup_provisioned(settings, sd, db)
                return HTMLResponse(
                    '<p class="text-red-500">Caddy route failed.</p>', status_code=502
                )

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
                "repo": safe_repo_url,
                "subdomain": sd.subdomain,
                "success": compose_ok,
            },
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    try:
        await db.commit()
    except Exception:
        await _cleanup_provisioned(settings, sd, db)
        raise

    if not compose_ok:
        err_esc = compose_error.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return HTMLResponse(
            '<div class="mt-3 p-4 rounded-lg border border-red-200 dark:border-red-800'
            ' bg-red-50 dark:bg-red-900/20">'
            '<p class="text-sm text-red-700 dark:text-red-400 font-medium">'
            "Docker compose failed</p>"
            f'<pre class="text-xs mt-2 text-red-500 max-h-32 overflow-auto">{err_esc}</pre>'
            "</div>"
        )

    from pit_panel.core.notifier import notify_app_deploy

    base_domain = sd.base_domain or _effective_domain(settings)
    fqdn = base_domain if sd.is_main_domain else f"{sd.subdomain}.{base_domain}"
    await notify_app_deploy(sd.subdomain, stack_type, fqdn)

    return HTMLResponse(
        '<div class="mt-3 p-4 rounded-lg border border-green-200 dark:border-green-800'
        ' bg-green-50 dark:bg-green-900/20">'
        '<p class="text-sm text-green-700 dark:text-green-400 font-medium">'
        f"Deployed to {fqdn}</p>"
        f'<a href="/apps/{sd.id}"'
        ' class="text-xs text-indigo-600 hover:underline mt-1 inline-block">'
        "Open app details &rarr;</a>"
        "</div>"
    )

"""Subdomain CRUD routes with Caddy integration and audit logging."""

import contextlib
import html
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.core.dns_check import root_problem
from pit_panel.core.dynu import DynuClient, available_roots
from pit_panel.db.models import AuditLog, Subdomain
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_user
from pit_panel.web.render import render

router = APIRouter()


def _dynu_enabled(settings: Any) -> bool:
    return all(
        isinstance(getattr(settings, key, ""), str) and getattr(settings, key).strip()
        for key in ("dynu_api_key", "dynu_domain")
    )


async def _dns_add(
    settings: Any, name: str, domain: str, ipv4: str | None = None
) -> tuple[int, str] | None:
    # Only a root the Dynu account actually owns can be provisioned.
    if not _dynu_enabled(settings):
        return None
    roots = await available_roots(settings)
    if roots is not None and domain not in roots:
        return None
    ip = ipv4 or settings._detect_ip()
    async with DynuClient(getattr(settings, "dynu_api_key", "")) as dynu:
        record = await dynu.add_a_record(domain, name, ip)
    return int(record["id"]), ip


async def _dns_delete(settings: Any, domain: str, record_id: int | None) -> None:
    if not _dynu_enabled(settings) or record_id is None:
        return
    roots = await available_roots(settings)
    if roots is not None and domain not in roots:
        return
    async with DynuClient(getattr(settings, "dynu_api_key", "")) as dynu:
        await dynu.delete_record(domain, record_id)


async def _log_audit(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None,
    details: dict[str, Any] | None,
    request: Request,
    *,
    commit: bool = True,
):
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(entry)
    if commit:
        await db.commit()


@router.get("/subdomains", response_class=HTMLResponse)
async def subdomains_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_user(request, db)

    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

        return RedirectResponse("/login", status_code=302)

    query = select(Subdomain).where(~Subdomain.is_main_domain)
    if not bool(getattr(user, "is_admin", False)):
        query = query.where(Subdomain.owner_user_id == user.id)
    result = await db.execute(query.order_by(Subdomain.created_at.desc()))
    subdomains = result.scalars().all()

    settings = get_settings()
    root_warning = None
    roots = None
    if _dynu_enabled(settings):
        roots = await available_roots(settings)
        root_warning = await root_problem(settings.dynu_domain)

    return render(
        "subdomains.html",
        user=user,
        subdomains=subdomains,
        error=None,
        created=request.query_params.get("created"),
        root_domain=settings.effective_domain,
        roots=roots,
        root_warning=root_warning,
    )


@router.post("/subdomains/add", response_class=HTMLResponse)
async def subdomain_add(
    request: Request,
    subdomain: str = Form(...),
    root: str = Form(""),
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
    if _dynu_enabled(settings) and not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Administrator privileges required")

    # The Dynu account owns the roots: a subdomain can live on any of them, not
    # only on the configured default one.
    base_domain = settings.effective_domain
    roots = await available_roots(settings) if _dynu_enabled(settings) else None
    if roots:
        chosen = (root or base_domain).strip().lower()
        if chosen not in roots:
            query = select(Subdomain).where(~Subdomain.is_main_domain)
            if not bool(getattr(user, "is_admin", False)):
                query = query.where(Subdomain.owner_user_id == user.id)
            result = await db.execute(query.order_by(Subdomain.created_at.desc()))
            return render(
                "subdomains.html",
                user=user,
                subdomains=result.scalars().all(),
                error=f"Unknown Dynu root: {chosen}. Available: {', '.join(roots)}",
                root_domain=base_domain,
                roots=roots,
            )
        base_domain = chosen

    safe_subdomain = subdomain.strip().lower().replace(" ", "-")
    if not safe_subdomain or not re.fullmatch(
        r"^[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$", safe_subdomain
    ):
        query = select(Subdomain).where(~Subdomain.is_main_domain)
        if not bool(getattr(user, "is_admin", False)):
            query = query.where(Subdomain.owner_user_id == user.id)
        result = await db.execute(
            query.order_by(Subdomain.created_at.desc())
        )
        subdomains = result.scalars().all()
        return render(
            "subdomains.html",
            user=user,
            subdomains=subdomains,
            error="Invalid subdomain name",
            root_domain=settings.effective_domain,
        )

    existing = await db.execute(
        select(Subdomain).where(
            Subdomain.subdomain == safe_subdomain,
            Subdomain.base_domain == base_domain,
        )
    )
    if existing.scalar_one_or_none():
        query = select(Subdomain).where(~Subdomain.is_main_domain)
        if not bool(getattr(user, "is_admin", False)):
            query = query.where(Subdomain.owner_user_id == user.id)
        result = await db.execute(
            query.order_by(Subdomain.created_at.desc())
        )
        subdomains = result.scalars().all()
        return render(
            "subdomains.html",
            user=user,
            subdomains=subdomains,
            error="Subdomain already exists",
            root_domain=settings.effective_domain,
        )

    # A name on its own has nothing to proxy: the Caddy route is created by the
    # app deployment, which knows the port. Creating it here pointed every new
    # subdomain at 127.0.0.1:80, so the URL handed to a customer was an error page.
    try:
        dns_record = await _dns_add(settings, safe_subdomain, base_domain)
    except Exception as exc:
        return HTMLResponse(
            f"DNS provisioning failed: {html.escape(str(exc))}", status_code=502
        )

    sd = Subdomain(
        subdomain=safe_subdomain,
        base_domain=base_domain,
        owner_user_id=user.id,
    )
    db.add(sd)
    try:
        await db.flush()
        if dns_record:
            sd.dynu_record_id, sd.dynu_ipv4 = dns_record
    except Exception as exc:
        await db.rollback()
        if dns_record:
            with contextlib.suppress(Exception):
                await _dns_delete(settings, base_domain, dns_record[0])
        return HTMLResponse(
            f"Subdomain persistence failed: {html.escape(str(exc))}", status_code=500
        )

    try:
        await _log_audit(
            db, user.id, "subdomain_create", "subdomain", sd.id,
            {"subdomain": safe_subdomain}, request,
        )
        await db.commit()
    except Exception as exc:
        if dns_record:
            with contextlib.suppress(Exception):
                await _dns_delete(settings, base_domain, dns_record[0])
        return HTMLResponse(
            f"Subdomain persistence failed: {html.escape(str(exc))}", status_code=500
        )

    fqdn = f"{safe_subdomain}.{base_domain}"
    return RedirectResponse(f"/subdomains?created={quote(fqdn)}", status_code=302)


@router.post("/subdomains/{sd_id}/edit", response_class=HTMLResponse)
async def subdomain_edit(
    request: Request,
    sd_id: int,
    subdomain: str = Form(...),
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
    if _dynu_enabled(settings) and not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd or sd.is_main_domain:
        return RedirectResponse("/subdomains", status_code=302)
    if not bool(getattr(user, "is_admin", False)) and sd.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this subdomain")
    new_name = subdomain.strip().lower().replace(" ", "-")
    old_name = sd.subdomain
    old_domain = sd.base_domain
    old_ipv4 = sd.dynu_ipv4

    name_valid = bool(re.fullmatch(r"^[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$", new_name))
    new_dns_record = None
    new_route_added = False
    old_route_removed = False
    if new_name and new_name != old_name and name_valid:
        clash = await db.execute(
            select(Subdomain).where(
                Subdomain.subdomain == new_name,
                Subdomain.base_domain == sd.base_domain,
                Subdomain.id != sd.id,
            )
        )
        if clash.scalar_one_or_none():
            return HTMLResponse("Subdomain already exists", status_code=409)
        dns_added = False
        try:
            new_dns_record = await _dns_add(settings, new_name, sd.base_domain)
            dns_added = new_dns_record is not None
            if sd.base_domain:
                caddy = CaddyManager(settings.caddy_admin_url)
                await caddy.remove_subdomain(old_name, sd.base_domain)
                old_route_removed = True
                await caddy.add_subdomain(
                    new_name, sd.base_domain, port=sd.host_port or 80
                )
                new_route_added = True
            await _dns_delete(settings, sd.base_domain, sd.dynu_record_id)
        except Exception as exc:
            if dns_added:
                with contextlib.suppress(Exception):
                    await _dns_delete(
                        settings, sd.base_domain, new_dns_record[0] if new_dns_record else None
                    )
            if new_route_added:
                with contextlib.suppress(Exception):
                    await CaddyManager(settings.caddy_admin_url).remove_subdomain(
                        new_name, sd.base_domain
                    )
            if old_route_removed:
                with contextlib.suppress(Exception):
                    await CaddyManager(settings.caddy_admin_url).add_subdomain(
                        old_name, sd.base_domain, port=sd.host_port or 80
                    )
            return HTMLResponse(
                f"DNS or Caddy provisioning failed: {html.escape(str(exc))}", status_code=502
            )
        sd.subdomain = new_name
        if new_dns_record:
            sd.dynu_record_id, sd.dynu_ipv4 = new_dns_record

    try:
        await _log_audit(
            db, user.id, "subdomain_edit", "subdomain", sd.id,
            {
                "old_subdomain": old_name,
                "new_subdomain": sd.subdomain,
            }, request,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if new_route_added:
            with contextlib.suppress(Exception):
                await CaddyManager(settings.caddy_admin_url).remove_subdomain(
                    new_name, old_domain
                )
        if new_dns_record:
            with contextlib.suppress(Exception):
                await _dns_delete(settings, old_domain, new_dns_record[0])
        if _dynu_enabled(settings):
            with contextlib.suppress(Exception):
                restored = await _dns_add(settings, old_name, old_domain, old_ipv4)
                if restored:
                    sd.dynu_record_id, sd.dynu_ipv4 = restored
                    await db.commit()
        if old_route_removed:
            with contextlib.suppress(Exception):
                await CaddyManager(settings.caddy_admin_url).add_subdomain(
                    old_name, old_domain, port=sd.host_port or 80
                )
        return HTMLResponse(
            f"Subdomain persistence failed: {html.escape(str(exc))}", status_code=500
        )

    return RedirectResponse("/subdomains", status_code=302)


@router.post("/subdomains/{sd_id}/delete", response_class=HTMLResponse)
async def subdomain_delete(
    request: Request,
    sd_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(request, db)

    if not user:
        if "hx-request" in request.headers:
            response = HTMLResponse("")

            response.headers["HX-Redirect"] = "/login"

            return response

        return RedirectResponse("/login", status_code=302)

    result = await db.execute(select(Subdomain).where(Subdomain.id == sd_id))
    sd = result.scalar_one_or_none()
    if not sd or sd.is_main_domain:
        return RedirectResponse("/subdomains", status_code=302)
    if not bool(getattr(user, "is_admin", False)) and sd.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this subdomain")
    settings = get_settings()
    if _dynu_enabled(settings) and not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Administrator privileges required")

    try:
        await _log_audit(
            db, user.id, "subdomain_delete", "subdomain", sd.id,
            {"subdomain": sd.subdomain}, request, commit=False,
        )
    except Exception as exc:
        return HTMLResponse(
            f"Subdomain audit failed: {html.escape(str(exc))}", status_code=500
        )

    old_name = sd.subdomain
    old_domain = sd.base_domain
    old_record_id = sd.dynu_record_id
    old_ipv4 = sd.dynu_ipv4
    dns_removed = False
    caddy_removed = False
    try:
        await _dns_delete(settings, old_domain, old_record_id)
        dns_removed = _dynu_enabled(settings) and old_record_id is not None
        if sd.base_domain:
            caddy = CaddyManager(settings.caddy_admin_url)
            if _dynu_enabled(settings):
                await caddy.remove_subdomain(sd.subdomain, sd.base_domain)
                caddy_removed = True
            else:
                with contextlib.suppress(Exception):
                    await caddy.remove_subdomain(sd.subdomain, sd.base_domain)
        await db.delete(sd)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if dns_removed:
            with contextlib.suppress(Exception):
                restored = await _dns_add(settings, old_name, old_domain, old_ipv4)
                if restored:
                    sd.dynu_record_id, sd.dynu_ipv4 = restored
                    await db.commit()
        if caddy_removed:
            with contextlib.suppress(Exception):
                await CaddyManager(settings.caddy_admin_url).add_subdomain(
                    old_name, old_domain
                )
        return HTMLResponse(
            f"DNS or Caddy provisioning failed: {html.escape(str(exc))}", status_code=502
        )

    return RedirectResponse("/subdomains", status_code=302)

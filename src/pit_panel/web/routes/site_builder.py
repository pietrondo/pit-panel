"""Site builder routes — drag&drop visual editor for static sites.

Bare-bones MVP: single-page sites with sections/columns/widgets (heading, text,
image, button, divider). No responsive preview, no style panel, no templates.
Output: static HTML served by an nginx container (per subdomain, like other
pit-panel apps).
"""

import contextlib
import html
import logging
import re
import secrets
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.db.models import Site
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

logger = logging.getLogger(__name__)
router = APIRouter()

WIDGET_TYPES = {"heading", "text", "image", "button", "divider"}
_PUBLISH_HTML_DIR = Path("/var/lib/pit-panel/published-sites")
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _to_subdomain(name: str) -> str:
    base = name.strip().lower().replace(" ", "-")
    base = re.sub(r"[^a-z0-9-]", "", base)
    base = base.strip("-")[:48] or "site"
    return f"{base}-{secrets.token_hex(2)}"


def _default_tree() -> dict[str, Any]:
    return {"sections": []}


def _published_site_dir(subdomain: str) -> Path:
    """Return a published-site directory guaranteed to stay under its root."""
    if not _SUBDOMAIN_RE.fullmatch(subdomain):
        raise ValueError("Invalid site subdomain")
    root = _PUBLISH_HTML_DIR.resolve()
    site_dir = (root / subdomain).resolve()
    if not site_dir.is_relative_to(root):
        raise ValueError("Published site path escapes root")
    return site_dir


def _safe_url(value: Any, default: str = "") -> str:
    url = str(value or "").strip()
    if not url:
        return default
    try:
        parsed = urlsplit(url)
    except ValueError:
        return default
    if url.startswith("//") or parsed.scheme.lower() not in {"", "http", "https"}:
        return default
    if parsed.scheme == "" and not url.startswith("/") and not url.startswith("#"):
        return default
    return url


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _validate_tree(tree: Any) -> dict[str, Any]:
    """Coerce/validate the widget tree; reject unknown widget types."""
    if not isinstance(tree, dict):
        return _default_tree()
    sections = tree.get("sections")
    if not isinstance(sections, list):
        return _default_tree()
    cleaned: list[dict[str, Any]] = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        cols = sec.get("columns")
        if not isinstance(cols, list):
            continue
        clean_cols: list[dict[str, Any]] = []
        for col in cols:
            if not isinstance(col, dict):
                continue
            widgets = col.get("widgets")
            if not isinstance(widgets, list):
                continue
            clean_widgets: list[dict[str, Any]] = []
            for w in widgets:
                if not isinstance(w, dict):
                    continue
                wtype = w.get("type")
                if wtype not in WIDGET_TYPES:
                    continue
                props = w.get("props")
                clean_widgets.append(
                    {
                        "id": str(w.get("id") or secrets.token_hex(6)),
                        "type": wtype,
                        "props": props if isinstance(props, dict) else {},
                    }
                )
            clean_cols.append(
                {
                    "id": str(col.get("id") or secrets.token_hex(6)),
                    "width": _bounded_int(col.get("width", 12), 12, 1, 12),
                    "widgets": clean_widgets,
                }
            )
        if clean_cols:
            cleaned.append(
                {"id": str(sec.get("id") or secrets.token_hex(6)), "columns": clean_cols}
            )
    return {"sections": cleaned}


def _render_widget(w: dict[str, Any]) -> str:
    props = w.get("props") or {}
    wtype = w.get("type")
    if wtype == "heading":
        level = _bounded_int(props.get("level", 2), 2, 1, 6)
        text = html.escape(str(props.get("text", "")))
        return f"<h{level}>{text}</h{level}>"
    if wtype == "text":
        text = html.escape(str(props.get("text", ""))).replace("\n", "<br>")
        return f"<p>{text}</p>"
    if wtype == "image":
        src = _safe_url(props.get("src"))
        alt = html.escape(str(props.get("alt", "")), quote=True)
        if not src:
            return ""
        return f'<img src="{html.escape(src, quote=True)}" alt="{alt}" loading="lazy">'
    if wtype == "button":
        text = html.escape(str(props.get("text", "Click")))
        url = html.escape(_safe_url(props.get("url"), "#"), quote=True)
        return f'<a href="{url}" class="sb-button">{text}</a>'
    if wtype == "divider":
        return '<hr class="sb-divider">'
    return ""


def _render_column(col: dict[str, Any]) -> str:
    widgets_html = "\n".join(_render_widget(w) for w in col.get("widgets", []))
    width = _bounded_int(col.get("width", 12), 12, 1, 12)
    return (
        f'<div class="sb-col" style="flex: 0 0 {width / 12 * 100:.2f}%; '
        f'max-width: {width / 12 * 100:.2f}%;">\n{widgets_html}\n</div>'
    )


def render_site_html(tree: dict[str, Any], site_name: str) -> str:
    """Render the full static HTML page from a widget tree."""
    sections_html: list[str] = []
    for sec in tree.get("sections", []):
        cols_html = "\n".join(_render_column(c) for c in sec.get("columns", []))
        sections_html.append(
            f'<section class="sb-section"><div class="sb-row">\n{cols_html}\n</div></section>'
        )
    body = "\n".join(sections_html) if sections_html else '<p class="sb-empty">Empty site</p>'
    title = html.escape(str(tree.get("title") or site_name))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; color: #1e293b; }}
.sb-section {{ padding: 2rem 1rem; }}
.sb-row {{ display: flex; flex-wrap: wrap; max-width: 1200px; margin: 0 auto; gap: 1rem; }}
.sb-col {{ box-sizing: border-box; }}
.sb-col img {{ max-width: 100%; height: auto; border-radius: 0.5rem; }}
.sb-col h1, .sb-col h2, .sb-col h3 {{ margin-top: 0; }}
.sb-button {{
  display: inline-block; padding: 0.6rem 1.2rem; background: #4f46e5;
  color: white; border-radius: 0.5rem; text-decoration: none;
}}
.sb-divider {{ border: none; border-top: 1px solid #e2e8f0; margin: 1.5rem 0; }}
.sb-empty {{ text-align: center; padding: 4rem 1rem; color: #94a3b8; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


@router.get("/site-builder", response_class=HTMLResponse)
async def site_builder_index(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    result = await db.execute(
        select(Site).where(Site.owner_user_id == user.id).order_by(Site.updated_at.desc())
    )
    sites = result.scalars().all()
    return render("site_builder.html", user=user, sites=sites, error=None)


@router.post("/site-builder/sites", response_class=HTMLResponse)
async def site_builder_create(
    request: Request,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    name = name.strip()
    if not name or len(name) > 128:
        result = await db.execute(
            select(Site).where(Site.owner_user_id == user.id).order_by(Site.updated_at.desc())
        )
        sites = result.scalars().all()
        return render(
            "site_builder.html",
            user=user,
            sites=sites,
            error="Name must be 1-128 characters",
        )

    subdomain = _to_subdomain(name)
    site = Site(
        owner_user_id=user.id,
        name=name,
        subdomain=subdomain,
        status="draft",
        widgets_json=_default_tree(),
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return RedirectResponse(f"/site-builder/sites/{site.id}/edit", status_code=302)


@router.get("/site-builder/sites/{site_id}/edit", response_class=HTMLResponse)
async def site_builder_edit(site_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")

    return render("site_builder_edit.html", user=user, site=site)


@router.post("/site-builder/sites/{site_id}/widgets")
async def site_builder_save_widgets(
    site_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        return JSONResponse({"error": "not_found"}, status_code=404)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    tree = _validate_tree(payload.get("tree") if isinstance(payload, dict) else payload)
    site.widgets_json = tree
    await db.commit()
    return JSONResponse({"status": "ok", "sections": len(tree["sections"])})


@router.post("/site-builder/sites/{site_id}/publish")
async def site_builder_publish(
    site_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        return JSONResponse({"error": "not_found"}, status_code=404)

    import datetime as dt

    html = render_site_html(site.widgets_json, site.name)
    try:
        pub_dir = _published_site_dir(site.subdomain)
        pub_dir.mkdir(parents=True, exist_ok=True)
        (pub_dir / "index.html").write_text(html, encoding="utf-8")
    except OSError as e:
        logger.exception("Failed to write published HTML for %s", site.subdomain)
        return JSONResponse({"error": "write_failed", "detail": str(e)}, status_code=500)

    settings = get_settings()
    caddy_note = ""
    if settings.base_domain:
        try:
            caddy = CaddyManager(settings.caddy_admin_url)
            await caddy.add_static_subdomain(site.subdomain, settings.base_domain, str(pub_dir))
        except Exception as e:
            logger.exception("Caddy route creation failed for %s", site.subdomain)
            caddy_note = f"Caddy route not configured: {e}"
    else:
        caddy_note = "base_domain not configured; HTML written but not routed."

    site.published_html_path = str(pub_dir / "index.html")
    site.published_at = dt.datetime.now(dt.UTC)
    site.status = "published"
    await db.commit()
    return JSONResponse(
        {
            "status": "published",
            "url": f"https://{site.subdomain}.{settings.base_domain}"
            if settings.base_domain
            else f"file://{site.published_html_path}",
            "path": site.published_html_path,
            "note": caddy_note,
        }
    )


@router.post("/site-builder/sites/{site_id}/delete")
async def site_builder_delete(
    site_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        return JSONResponse({"error": "not_found"}, status_code=404)

    if site.published_html_path:
        with contextlib.suppress(OSError):
            pub_dir = _published_site_dir(site.subdomain)
            published_path = Path(site.published_html_path).resolve()
            if published_path == pub_dir / "index.html":
                shutil.rmtree(pub_dir, ignore_errors=True)

    settings = get_settings()
    if settings.base_domain:
        with contextlib.suppress(Exception):
            await CaddyManager(settings.caddy_admin_url).remove_static_subdomain(
                site.subdomain, settings.base_domain
            )

    await db.delete(site)
    await db.commit()
    return RedirectResponse("/site-builder", status_code=302)

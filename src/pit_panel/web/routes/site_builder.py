"""Site builder routes — drag&drop visual editor for static sites.

Single-page sites with sections/columns/widgets (heading, text, image, button,
divider). Per-widget style props (colors, alignment, spacing, typography) are
merged into the rendered HTML, and the editor supports live preview via iframe.
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
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.core.caddy import CaddyManager
from pit_panel.db.models import Page, Site
from pit_panel.db.session import get_db
from pit_panel.web.deps import get_admin
from pit_panel.web.render import render

logger = logging.getLogger(__name__)
router = APIRouter()

WIDGET_TYPES = {"heading", "text", "image", "button", "divider"}
_PUBLISH_HTML_DIR = Path("/var/lib/pit-panel/published-sites")
_UPLOAD_DIR = Path("/var/lib/pit-panel/site-assets")
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}

# Style props accepted per widget type, coerced through a bounded whitelist.
# True = free-form value still filtered by _safe_css_value; a set = enum values.
_STYLE_KEYS: dict[str, Literal[True] | set[str]] = {
    "align": {"left", "center", "right"},
    "color": True,
    "bg": True,
    "size": True,
    "weight": {"normal", "bold"},
    "padding": True,
    "margin": True,
    "radius": True,
}
_SECTION_STYLE_KEYS: set[str] = {"bg", "padding", "color", "align"}


def _style_value_allowed(key: str, value: Any) -> bool:
    constraint = _STYLE_KEYS.get(key)
    if constraint is True:
        return True
    if isinstance(constraint, set):
        return str(value).lower() in constraint
    return False


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


_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
HOME_SLUG = "home"


def _to_slug(name: str, taken: set[str]) -> str:
    """Derive a unique, URL-safe page slug from a display name."""
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:48] or "page"
    if base == HOME_SLUG:
        base = "home-page"
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def _published_filename(slug: str) -> str:
    """The slug `home` owns the site root; every other slug gets its own file."""
    return "index.html" if slug == HOME_SLUG else f"{slug}.html"


def _page_href(slug: str, base_url: str = "") -> str:
    """Public link to a page, relative to the published site (or preview)."""
    prefix = f"{base_url}/" if base_url else ""
    return f"{prefix}sites/{slug}" if base_url else _published_filename(slug)


async def _site_pages(db: AsyncSession, site: Site) -> list[Page]:
    """Return the site's pages, seeding `home` from legacy widgets_json once.

    Sites created before multi-page support only carry `Site.widgets_json`, so
    the first access materializes it as the `home` page without data loss.
    """
    result = await db.execute(
        select(Page).where(Page.site_id == site.id).order_by(Page.sort_order, Page.id)
    )
    pages = list(result.scalars().all())
    if not pages:
        home = Page(
            site_id=site.id,
            slug=HOME_SLUG,
            title=site.name,
            widgets_json=_validate_tree(site.widgets_json),
            sort_order=0,
        )
        db.add(home)
        await db.commit()
        await db.refresh(home)
        pages = [home]
    return pages


async def _resolve_page(db: AsyncSession, site: Site, slug: str | None) -> tuple[Page, list[Page]]:
    """Resolve one page by slug (defaulting to `home`) plus the full page list."""
    pages = await _site_pages(db, site)
    wanted = slug if slug in {p.slug for p in pages} else HOME_SLUG
    page = next(p for p in pages if p.slug == wanted)
    return page, pages


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


_CSS_VALUE_RE = re.compile(r"^[#a-zA-Z0-9\s,.%\-/()]+$")


def _safe_css_value(value: Any) -> str:
    """Allow only simple CSS values; block url(), expressions, quotes, markup."""
    text = str(value or "").strip()
    if not text or len(text) > 64:
        return ""
    lowered = text.lower()
    bad_tokens = ("url(", "expression", "javascript:", "\"", "'", "<", ">", ";")
    if any(bad in lowered for bad in bad_tokens):
        return ""
    if not _CSS_VALUE_RE.fullmatch(text):
        return ""
    return text


def _safe_style(props: Any, allowed: dict[str, Any] | set[str]) -> str:
    """Build a safe inline `style` attribute from whitelisted style props.

    `allowed` may be a mapping of key -> constraint (True = free-form value that
    still goes through `_safe_css_value`, a set = allowed enum values), or a
    plain set of keys treated as free-form.
    """
    if not isinstance(props, dict):
        return ""
    rules: dict[str, Literal[True] | set[str]] = (
        dict.fromkeys(allowed, True) if isinstance(allowed, set) else allowed
    )
    decls: list[str] = []
    for key, constraint in rules.items():
        raw = props.get(key)
        if raw is None:
            continue
        if constraint is True:
            value = _safe_css_value(raw)
        else:
            value = str(raw).strip().lower()
            if value not in constraint:
                continue
        if not value:
            continue
        if key == "align":
            decls.append(f"text-align: {value}")
        elif key == "color":
            decls.append(f"color: {value}")
        elif key == "bg":
            decls.append(f"background-color: {value}")
        elif key == "size":
            decls.append(f"font-size: {value}")
        elif key == "weight":
            decls.append(f"font-weight: {value}")
        elif key == "padding":
            decls.append(f"padding: {value}")
        elif key == "margin":
            decls.append(f"margin: {value}")
        elif key == "radius":
            decls.append(f"border-radius: {value}")
    return f' style="{"; ".join(decls)}"' if decls else ""


def _validate_tree(tree: Any) -> dict[str, Any]:
    """Coerce/validate the widget tree; reject unknown widget types."""
    if not isinstance(tree, dict):
        return _default_tree()
    sections = tree.get("sections")
    if not isinstance(sections, list):
        return _default_tree()
    result: dict[str, Any] = {"sections": []}
    title = tree.get("title")
    if isinstance(title, str) and title.strip():
        result["title"] = title.strip()[:200]
    custom_css = tree.get("custom_css")
    if isinstance(custom_css, str) and custom_css.strip():
        result["custom_css"] = custom_css[:10000]
    cleaned = result["sections"]
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
                style = w.get("style")
                clean_widgets.append(
                    {
                        "id": str(w.get("id") or secrets.token_hex(6)),
                        "type": wtype,
                        "props": props if isinstance(props, dict) else {},
                        "style": {
                            k: v
                            for k, v in (style or {}).items()
                            if k in _STYLE_KEYS
                            and isinstance(v, (str, int, float))
                            and _style_value_allowed(k, v)
                        }
                        if isinstance(style, dict)
                        else {},
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
            sec_style = sec.get("style")
            cleaned.append(
                {
                    "id": str(sec.get("id") or secrets.token_hex(6)),
                    "columns": clean_cols,
                    "style": {
                        k: v
                        for k, v in (sec_style or {}).items()
                        if k in _SECTION_STYLE_KEYS and isinstance(v, (str, int, float))
                    }
                    if isinstance(sec_style, dict)
                    else {},
                }
            )
    return result


def _render_widget(w: dict[str, Any]) -> str:
    props = w.get("props") or {}
    wtype = w.get("type")
    style = _safe_style(w.get("style"), _STYLE_KEYS)
    if wtype == "heading":
        level = _bounded_int(props.get("level", 2), 2, 1, 6)
        text = html.escape(str(props.get("text", "")))
        return f"<h{level}{style}>{text}</h{level}>"
    if wtype == "text":
        text = html.escape(str(props.get("text", ""))).replace("\n", "<br>")
        return f"<p{style}>{text}</p>"
    if wtype == "image":
        src = _safe_url(props.get("src"))
        alt = html.escape(str(props.get("alt", "")), quote=True)
        if not src:
            return ""
        return (
            f'<img src="{html.escape(src, quote=True)}" alt="{alt}" loading="lazy"{style}>'
        )
    if wtype == "button":
        text = html.escape(str(props.get("text", "Click")))
        url = html.escape(_safe_url(props.get("url"), "#"), quote=True)
        return f'<a href="{url}" class="sb-button"{style}>{text}</a>'
    if wtype == "divider":
        return f'<hr class="sb-divider"{style}>'
    return ""


def _render_column(col: dict[str, Any]) -> str:
    widgets_html = "\n".join(_render_widget(w) for w in col.get("widgets", []))
    width = _bounded_int(col.get("width", 12), 12, 1, 12)
    return (
        f'<div class="sb-col" style="flex: 0 0 {width / 12 * 100:.2f}%; '
        f'max-width: {width / 12 * 100:.2f}%;">\n{widgets_html}\n</div>'
    )


def render_site_html(
    tree: dict[str, Any],
    site_name: str,
    base_url: str = "",
    nav_pages: list[dict[str, str]] | None = None,
) -> str:
    """Render the full static HTML page from a widget tree.

    `base_url` is prepended to root-relative asset URLs so the same tree renders
    correctly both in the editor preview (served from /site-builder/... ) and on
    the published subdomain.

    `nav_pages` renders a cross-page navigation bar; each entry is
    `{"slug", "title", "href"}` and the entry matching `tree["nav_current"]`
    (or the slug whose href is `index.html` failing that) is marked current.
    """
    sections_html: list[str] = []
    for sec in tree.get("sections", []):
        cols_html = "\n".join(_render_column(c) for c in sec.get("columns", []))
        sec_style = _safe_style(sec.get("style"), _SECTION_STYLE_KEYS)
        sections_html.append(
            f'<section class="sb-section"{sec_style}>'
            f'<div class="sb-row">\n{cols_html}\n</div></section>'
        )
    body = "\n".join(sections_html) if sections_html else '<p class="sb-empty">Empty site</p>'
    title = html.escape(str(tree.get("title") or site_name))
    current = str(tree.get("nav_current") or "")
    if nav_pages and len(nav_pages) > 1:
        links = []
        for p in nav_pages:
            href = html.escape(p["href"], quote=True)
            label = html.escape(p["title"] or p["slug"])
            cls = "sb-nav-link sb-nav-current" if p["slug"] == current else "sb-nav-link"
            links.append(f'<a class="{cls}" href="{href}">{label}</a>')
        nav_html = f'<nav class="sb-nav">{"".join(links)}</nav>'
    else:
        nav_html = ""
    custom_css = str(tree.get("custom_css") or "")[:10000]
    css_block = f"<style>{custom_css}</style>" if custom_css else ""
    if base_url:
        body = re.sub(r'(src|href)="/(?!/)', rf'\1="{base_url}/', body)
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
.sb-nav {{
  display: flex; flex-wrap: wrap; gap: 1.25rem; align-items: center;
  max-width: 1200px; margin: 0 auto; padding: 1rem 1rem 0;
}}
.sb-nav-link {{ color: #4f46e5; text-decoration: none; font-weight: 500; }}
.sb-nav-link:hover {{ text-decoration: underline; }}
.sb-nav-current {{ color: #1e293b; font-weight: 700; }}
</style>
{css_block}
</head>
<body>
{nav_html}
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
async def site_builder_edit(
    site_id: int,
    request: Request,
    page: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")

    current, pages = await _resolve_page(db, site, page)
    return render(
        "site_builder_edit.html",
        user=user,
        site=site,
        page=current,
        pages=pages,
    )


@router.get("/site-builder/sites/{site_id}/widgets")
async def site_builder_get_widgets(
    site_id: int,
    request: Request,
    page: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        return JSONResponse({"error": "not_found"}, status_code=404)

    current, pages = await _resolve_page(db, site, page)
    return JSONResponse(
        {
            "tree": _validate_tree(current.widgets_json),
            "page": {"slug": current.slug, "title": current.title},
            "pages": [{"slug": p.slug, "title": p.title} for p in pages],
        }
    )


@router.get("/site-builder/sites/{site_id}/preview", response_class=HTMLResponse)
async def site_builder_preview(
    site_id: int,
    request: Request,
    page: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")

    current, pages = await _resolve_page(db, site, page)
    tree = _validate_tree(current.widgets_json)
    tree["nav_current"] = current.slug
    nav = [
        {"slug": p.slug, "title": p.title, "href": _page_href(p.slug, base_url="/site-builder")}
        for p in pages
    ]
    return HTMLResponse(
        render_site_html(tree, site.name, base_url="/site-builder", nav_pages=nav)
    )


@router.get("/site-builder/assets/{site_id}/{filename}")
async def site_builder_asset(
    site_id: int, filename: str, request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")

    from fastapi.responses import FileResponse

    assets_root = (_UPLOAD_DIR / str(site_id)).resolve()
    target = (assets_root / Path(filename).name).resolve()
    if not target.is_relative_to(assets_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


@router.post("/site-builder/sites/{site_id}/upload")
async def site_builder_upload(
    site_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        return JSONResponse({"error": "not_found"}, status_code=404)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        return JSONResponse({"error": "unsupported_type"}, status_code=400)

    assets_dir = _UPLOAD_DIR / str(site_id)
    try:
        assets_dir.mkdir(parents=True, exist_ok=True)
        name = f"{secrets.token_hex(8)}{ext}"
        target = assets_dir / name
        with target.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                fh.write(chunk)
    except OSError as e:
        logger.exception("Site asset upload failed for site %s", site_id)
        return JSONResponse({"error": "write_failed", "detail": str(e)}, status_code=500)

    return JSONResponse({"status": "ok", "url": f"/site-builder/assets/{site_id}/{name}"})


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

    slug = payload.get("page") if isinstance(payload, dict) else None
    current, _ = await _resolve_page(db, site, slug)
    tree = _validate_tree(payload.get("tree") if isinstance(payload, dict) else payload)
    current.widgets_json = tree
    if isinstance(tree.get("title"), str) and tree["title"].strip():
        current.title = tree["title"].strip()[:200]
    if isinstance(tree.get("page_slug"), str):
        requested = tree["page_slug"].strip().lower()
        if _SLUG_RE.fullmatch(requested) and requested != current.slug:
            taken = {
                s
                for (s,) in (
                    await db.execute(select(Page.slug).where(Page.site_id == site.id))
                ).all()
            }
            if requested not in taken:
                current.slug = requested
    await db.commit()
    return JSONResponse(
        {"status": "ok", "sections": len(tree["sections"]), "slug": current.slug}
    )


@router.post("/site-builder/sites/{site_id}/pages")
async def site_builder_add_page(
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

    name = str((payload or {}).get("title") or "").strip()
    if not name or len(name) > 200:
        return JSONResponse({"error": "title must be 1-200 characters"}, status_code=400)

    pages = await _site_pages(db, site)
    slug = _to_slug(name, {p.slug for p in pages})
    next_order = max((p.sort_order for p in pages), default=-1) + 1
    new_page = Page(
        site_id=site.id,
        slug=slug,
        title=name,
        widgets_json=_default_tree(),
        sort_order=next_order,
    )
    db.add(new_page)
    await db.commit()
    await db.refresh(new_page)
    return JSONResponse({"status": "ok", "slug": new_page.slug, "title": new_page.title})


@router.post("/site-builder/sites/{site_id}/pages/{slug}/delete")
async def site_builder_delete_page(
    site_id: int,
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    site = await db.get(Site, site_id)
    if not site or site.owner_user_id != user.id:
        return JSONResponse({"error": "not_found"}, status_code=404)

    pages = await _site_pages(db, site)
    if slug == HOME_SLUG:
        return JSONResponse({"error": "cannot_delete_home"}, status_code=400)
    target = next((p for p in pages if p.slug == slug), None)
    if not target:
        return JSONResponse({"error": "not_found"}, status_code=404)

    await db.delete(target)
    await db.commit()
    return JSONResponse({"status": "ok"})


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

    pages = await _site_pages(db, site)
    pub_dir = _published_site_dir(site.subdomain)
    nav = [
        {"slug": p.slug, "title": p.title, "href": _published_filename(p.slug)} for p in pages
    ]
    written: list[str] = []
    try:
        pub_dir.mkdir(parents=True, exist_ok=True)
        for p in pages:
            tree = _validate_tree(p.widgets_json)
            tree["nav_current"] = p.slug
            html_out = render_site_html(tree, site.name, nav_pages=nav if len(pages) > 1 else None)
            filename = _published_filename(p.slug)
            (pub_dir / filename).write_text(html_out, encoding="utf-8")
            written.append(filename)
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
            "pages": written,
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

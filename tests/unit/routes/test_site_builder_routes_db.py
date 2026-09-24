"""Route + rendering tests for the Site Builder rework.

Covers the missing GET /widgets route, per-widget style merging, site settings
(title, custom CSS), image upload, and asset serving.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Base, Site, User
from pit_panel.web.app import create_app
from pit_panel.web.routes.site_builder import (
    _safe_css_value,
    _safe_style,
    render_site_html,
)

SAMPLE_TREE = {
    "sections": [
        {
            "id": "sec1",
            "style": {"bg": "#f8fafc", "padding": "3rem 1rem"},
            "columns": [
                {
                    "id": "col1",
                    "width": 12,
                    "widgets": [
                        {
                            "id": "w1",
                            "type": "heading",
                            "props": {"text": "Hello", "level": 1},
                            "style": {"color": "#ff0000", "align": "center", "size": "3rem"},
                        },
                        {
                            "id": "w2",
                            "type": "text",
                            "props": {"text": "Body"},
                            "style": {"weight": "bold"},
                        },
                    ],
                }
            ],
        }
    ]
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url="sqlite+aiosqlite://",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=None)

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("pit_panel.db.session._engine", engine)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", sessionmaker)
    monkeypatch.setattr("pit_panel.web.routes.site_builder._UPLOAD_DIR", tmp_path)

    app = create_app(s)
    return TestClient(app)


@pytest.fixture
def auth_user(monkeypatch):
    async def mock_get_admin(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.site_builder.get_admin", mock_get_admin)


async def _seed_site(tree, owner_user_id=1, name="Demo"):
    from pit_panel.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        site = Site(
            owner_user_id=owner_user_id,
            name=name,
            subdomain="demo",
            status="draft",
            widgets_json=tree,
        )
        db.add(site)
        await db.commit()
        await db.refresh(site)
        return site.id


class TestSafeCssValue:
    def test_accepts_hex_and_simple_values(self):
        assert _safe_css_value("#ff0000") == "#ff0000"
        assert _safe_css_value("3rem") == "3rem"
        assert _safe_css_value("2rem 1rem") == "2rem 1rem"
        assert _safe_css_value("rgba(0,0,0,0.5)") == "rgba(0,0,0,0.5)"

    @pytest.mark.parametrize(
        "bad",
        [
            "url(http://evil.test/x.png)",
            "expression(alert(1))",
            "javascript:alert(1)",
            'red"; background:url(',
            "<script>",
            "a;b",
        ],
    )
    def test_rejects_dangerous_values(self, bad):
        assert _safe_css_value(bad) == ""

    def test_rejects_overlong_value(self):
        assert _safe_css_value("a" * 100) == ""


class TestSafeStyle:
    def test_builds_whitelisted_declarations(self):
        allowed = {"color": True, "align": {"left", "center"}}
        out = _safe_style({"color": "#fff", "align": "center"}, allowed)
        assert out == ' style="color: #fff; text-align: center"'

    def test_ignores_disallowed_enum_value(self):
        assert _safe_style({"align": "diagonal"}, {"align": {"left", "center"}}) == ""

    def test_non_dict_returns_empty(self):
        assert _safe_style("nope", {"color": True}) == ""

    def test_injection_via_style_is_dropped(self):
        assert _safe_style({"color": 'red" onload="x'}, {"color": True}) == ""


class TestRenderStyleMerging:
    def test_widget_styles_appear_inline(self):
        out = render_site_html(SAMPLE_TREE, "Demo")
        assert "color: #ff0000" in out
        assert "text-align: center" in out
        assert "font-size: 3rem" in out
        assert "font-weight: bold" in out

    def test_section_style_applied(self):
        out = render_site_html(SAMPLE_TREE, "Demo")
        assert "background-color: #f8fafc" in out
        assert "padding: 3rem 1rem" in out

    def test_malicious_style_is_stripped_from_output(self):
        tree = {
            "sections": [
                {
                    "id": "s",
                    "columns": [
                        {
                            "id": "c",
                            "widgets": [
                                {
                                    "id": "w",
                                    "type": "text",
                                    "props": {"text": "x"},
                                    "style": {"color": 'url("javascript:alert(1)")'},
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        out = render_site_html(tree, "Demo")
        assert "javascript:" not in out

    def test_base_url_rewrites_root_relative_assets(self):
        tree = {
            "sections": [
                {
                    "id": "s",
                    "columns": [
                        {
                            "id": "c",
                            "widgets": [
                                {
                                    "id": "w",
                                    "type": "image",
                                    "props": {"src": "/site-builder/assets/1/x.png"},
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        out = render_site_html(tree, "Demo", base_url="/site-builder")
        assert 'src="/site-builder/site-builder/assets/1/x.png"' in out

    def test_base_url_does_not_double_rewrite_scheme_urls(self):
        tree = {
            "sections": [
                {
                    "id": "s",
                    "columns": [
                        {
                            "id": "c",
                            "widgets": [
                                {
                                    "id": "w",
                                    "type": "image",
                                    "props": {"src": "https://cdn.test/a.png"},
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        out = render_site_html(tree, "Demo", base_url="/site-builder")
        assert "https://cdn.test/a.png" in out
        assert "/site-builder/https" not in out


class TestSiteSettings:
    def test_custom_title_rendered(self):
        out = render_site_html({**SAMPLE_TREE, "title": "My Page"}, "Demo")
        assert "<title>My Page</title>" in out

    def test_title_falls_back_to_site_name(self):
        out = render_site_html(SAMPLE_TREE, "Fallback")
        assert "<title>Fallback</title>" in out

    def test_custom_css_injected(self):
        out = render_site_html({**SAMPLE_TREE, "custom_css": ".x { color: red; }"}, "Demo")
        assert "<style>.x { color: red; }</style>" in out

    def test_no_custom_css_no_style_block(self):
        out = render_site_html(SAMPLE_TREE, "Demo")
        assert "<style>.x" not in out


class TestValidateTreePreservesSettings:
    def test_title_and_custom_css_survive_validation(self):
        from pit_panel.web.routes.site_builder import _validate_tree

        result = _validate_tree({**SAMPLE_TREE, "title": " T ", "custom_css": ".a{}"})
        assert result["title"] == "T"
        assert result["custom_css"] == ".a{}"

    def test_bogus_settings_are_dropped(self):
        from pit_panel.web.routes.site_builder import _validate_tree

        result = _validate_tree({**SAMPLE_TREE, "title": 5, "custom_css": []})
        assert "title" not in result
        assert "custom_css" not in result

    def test_widget_style_whitelist_enforced(self):
        from pit_panel.web.routes.site_builder import _validate_tree

        tree = {
            "sections": [
                {
                    "id": "s",
                    "columns": [
                        {
                            "id": "c",
                            "widgets": [
                                {
                                    "id": "w",
                                    "type": "text",
                                    "props": {},
                                    "style": {"color": "#fff", "evil": "x", "align": "nope"},
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        w = _validate_tree(tree)["sections"][0]["columns"][0]["widgets"][0]
        assert w["style"] == {"color": "#fff"}


class TestWidgetsGetRoute:
    def test_returns_default_tree_for_empty_site(self, client, auth_user):
        site_id = asyncio.run(_seed_site({}))
        resp = client.get(f"/site-builder/sites/{site_id}/widgets")
        assert resp.status_code == 200
        assert "sections" in resp.json()["tree"]

    def test_returns_saved_tree_with_styles(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        resp = client.get(f"/site-builder/sites/{site_id}/widgets")
        assert resp.status_code == 200
        widgets = resp.json()["tree"]["sections"][0]["columns"][0]["widgets"]
        assert widgets[0]["style"]["color"] == "#ff0000"

    def test_missing_site_returns_404(self, client, auth_user):
        assert client.get("/site-builder/sites/999/widgets").status_code == 404

    def test_other_users_site_returns_404(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE, owner_user_id=42))
        assert client.get(f"/site-builder/sites/{site_id}/widgets").status_code == 404


async def _seed_pages(site_id, slugs):
    from pit_panel.db.models import Page
    from pit_panel.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        for i, slug in enumerate(slugs):
            db.add(
                Page(
                    site_id=site_id,
                    slug=slug,
                    title=slug.title(),
                    widgets_json=SAMPLE_TREE,
                    sort_order=i,
                )
            )
        await db.commit()


class TestPreviewRoute:
    def test_preview_renders_saved_styles(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        resp = client.get(f"/site-builder/sites/{site_id}/preview")
        assert resp.status_code == 200
        assert "color: #ff0000" in resp.text

    def test_preview_nav_links_point_to_preview(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        asyncio.run(_seed_pages(site_id, ["home", "about"]))
        resp = client.get(f"/site-builder/sites/{site_id}/preview")
        assert resp.status_code == 200
        assert f'href="/site-builder/sites/{site_id}/preview?page=home"' in resp.text
        assert f'href="/site-builder/sites/{site_id}/preview?page=about"' in resp.text
        assert "/site-builder/sites/home" not in resp.text

    def test_preview_missing_site_404(self, client, auth_user):
        assert client.get("/site-builder/sites/999/preview").status_code == 404

    def test_preview_frame_header_allows_same_origin(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        resp = client.get(f"/site-builder/sites/{site_id}/preview")
        assert resp.headers["x-frame-options"] == "SAMEORIGIN"

    def test_non_preview_frame_header_denies(self, client, auth_user):
        assert client.get("/login").headers["x-frame-options"] == "DENY"


class TestUploadRoute:
    def test_rejects_non_image_extension(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        resp = client.post(
            f"/site-builder/sites/{site_id}/upload",
            files={"file": ("evil.sh", b"#!/bin/sh", "application/x-sh")},
        )
        assert resp.status_code == 400

    def test_stores_image_and_returns_url(self, client, auth_user, tmp_path):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        resp = client.post(
            f"/site-builder/sites/{site_id}/upload",
            files={"file": ("pic.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert url.startswith(f"/site-builder/assets/{site_id}/")
        assert (tmp_path / str(site_id)).is_dir()

    def test_upload_requires_ownership(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE, owner_user_id=42))
        resp = client.post(
            f"/site-builder/sites/{site_id}/upload",
            files={"file": ("pic.png", b"x", "image/png")},
        )
        assert resp.status_code == 404

    def test_file_size_is_bounded_by_streaming(self, client, auth_user, tmp_path):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        payload = b"a" * (3 * 1024 * 1024)
        resp = client.post(
            f"/site-builder/sites/{site_id}/upload",
            files={"file": ("big.png", payload, "image/png")},
        )
        assert resp.status_code == 200
        stored = list((tmp_path / str(site_id)).iterdir())
        assert stored[0].stat().st_size == len(payload)


class TestAssetRoute:
    def test_serves_uploaded_file(self, client, auth_user, tmp_path):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        assets = tmp_path / str(site_id)
        assets.mkdir(parents=True)
        (assets / "a.png").write_bytes(b"\x89PNG")
        resp = client.get(f"/site-builder/assets/{site_id}/a.png")
        assert resp.status_code == 200
        assert resp.content == b"\x89PNG"

    def test_traversal_attempt_is_blocked(self, client, auth_user, tmp_path):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        secret = tmp_path / "secret.txt"
        secret.write_text("nope")
        resp = client.get(f"/site-builder/assets/{site_id}/..%2Fsecret.txt")
        assert resp.status_code in (404, 400)

    def test_missing_asset_404(self, client, auth_user):
        site_id = asyncio.run(_seed_site(SAMPLE_TREE))
        assert client.get(f"/site-builder/assets/{site_id}/none.png").status_code == 404


class TestSaveRoute:
    def test_save_then_get_roundtrip_keeps_settings(self, client, auth_user):
        site_id = asyncio.run(_seed_site({}))
        payload = {**SAMPLE_TREE, "title": "Saved", "custom_css": ".a{color:red}"}
        resp = client.post(f"/site-builder/sites/{site_id}/widgets", json={"tree": payload})
        assert resp.status_code == 200
        got = client.get(f"/site-builder/sites/{site_id}/widgets").json()["tree"]
        assert got["title"] == "Saved"
        assert got["custom_css"] == ".a{color:red}"
        assert got["sections"][0]["style"]["bg"] == "#f8fafc"

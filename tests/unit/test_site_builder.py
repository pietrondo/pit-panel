"""Tests for the site builder module: validation, widget rendering, static HTML output."""

from pit_panel.web.routes.site_builder import (
    WIDGET_TYPES,
    _default_tree,
    _validate_tree,
    render_site_html,
)


def test_default_tree_empty():
    tree = _default_tree()
    assert tree == {"sections": []}


def test_validate_tree_drops_unknown_widget_types():
    tree = {
        "sections": [
            {
                "id": "s1",
                "columns": [
                    {
                        "id": "c1",
                        "width": 12,
                        "widgets": [
                            {"id": "w1", "type": "heading", "props": {"text": "Hi", "level": 1}},
                            {"id": "w2", "type": "youtube", "props": {"url": "x"}},
                        ],
                    }
                ],
            }
        ]
    }
    cleaned = _validate_tree(tree)
    assert len(cleaned["sections"]) == 1
    widgets = cleaned["sections"][0]["columns"][0]["widgets"]
    assert len(widgets) == 1
    assert widgets[0]["type"] == "heading"
    assert widgets[0]["props"]["text"] == "Hi"


def test_validate_tree_strips_non_dict_widgets():
    tree = {
        "sections": [
            {
                "id": "s",
                "columns": [
                    {
                        "id": "c",
                        "width": 6,
                        "widgets": [None, "bad", {"type": "text", "props": {"text": "ok"}}],
                    }
                ],
            }
        ]
    }
    cleaned = _validate_tree(tree)
    widgets = cleaned["sections"][0]["columns"][0]["widgets"]
    assert len(widgets) == 1
    assert widgets[0]["type"] == "text"


def test_validate_tree_non_dict_input():
    assert _validate_tree(None) == {"sections": []}
    assert _validate_tree("bad") == {"sections": []}
    assert _validate_tree([1, 2]) == {"sections": []}


def test_validate_tree_clamps_width():
    tree = {"sections": [{"id": "s", "columns": [{"id": "c", "width": 99, "widgets": []}]}]}
    cleaned = _validate_tree(tree)
    assert cleaned["sections"][0]["columns"][0]["width"] == 12


def test_validate_tree_handles_invalid_width():
    tree = {"sections": [{"columns": [{"width": "bad", "widgets": []}]}]}
    assert _validate_tree(tree)["sections"][0]["columns"][0]["width"] == 12


def test_widget_types_complete():
    expected = {"heading", "text", "image", "button", "divider"}
    assert expected == WIDGET_TYPES


def test_render_widget_heading():
    html = render_site_html({"sections": []}, "x")
    out = html
    assert "<title>x</title>" in out
    assert "Empty site" in out


def test_render_widget_heading_h1():
    from pit_panel.web.routes.site_builder import _render_widget

    out = _render_widget({"type": "heading", "props": {"text": "Hello", "level": 1}})
    assert out == "<h1>Hello</h1>"


def test_render_widget_escapes_markup():
    from pit_panel.web.routes.site_builder import _render_widget

    out = _render_widget({"type": "heading", "props": {"text": "<script>alert(1)</script>"}})
    assert out == "<h2>&lt;script&gt;alert(1)&lt;/script&gt;</h2>"


def test_render_widget_heading_clamps_level():
    from pit_panel.web.routes.site_builder import _render_widget

    assert _render_widget({"type": "heading", "props": {"text": "x", "level": 99}}) == "<h6>x</h6>"
    assert _render_widget({"type": "heading", "props": {"text": "x", "level": 0}}) == "<h1>x</h1>"
    assert (
        _render_widget({"type": "heading", "props": {"text": "x", "level": "bad"}}) == "<h2>x</h2>"
    )


def test_render_widget_text_multiline():
    from pit_panel.web.routes.site_builder import _render_widget

    out = _render_widget({"type": "text", "props": {"text": "line1\nline2"}})
    assert out == "<p>line1<br>line2</p>"


def test_render_widget_image_with_src():
    from pit_panel.web.routes.site_builder import _render_widget

    out = _render_widget({"type": "image", "props": {"src": "/img.png", "alt": "alt"}})
    assert out == '<img src="/img.png" alt="alt" loading="lazy">'


def test_render_widget_rejects_unsafe_urls_and_escapes_attributes():
    from pit_panel.web.routes.site_builder import _render_widget

    assert _render_widget({"type": "button", "props": {"url": "javascript:alert(1)"}}) == (
        '<a href="#" class="sb-button">Click</a>'
    )
    out = _render_widget({"type": "image", "props": {"src": "/x?a=1&b=2", "alt": '"x"'}})
    assert out == '<img src="/x?a=1&amp;b=2" alt="&quot;x&quot;" loading="lazy">'


def test_render_widget_image_no_src_returns_empty():
    from pit_panel.web.routes.site_builder import _render_widget

    assert _render_widget({"type": "image", "props": {"src": ""}}) == ""


def test_render_widget_button():
    from pit_panel.web.routes.site_builder import _render_widget

    out = _render_widget({"type": "button", "props": {"text": "Go", "url": "/x"}})
    assert out == '<a href="/x" class="sb-button">Go</a>'


def test_render_widget_divider():
    from pit_panel.web.routes.site_builder import _render_widget

    assert _render_widget({"type": "divider"}) == '<hr class="sb-divider">'


def test_render_column_width_percent():
    from pit_panel.web.routes.site_builder import _render_column

    out = _render_column({"width": 6, "widgets": []})
    assert "flex: 0 0 50.00%" in out
    assert "max-width: 50.00%" in out


def test_render_site_html_full_page():
    tree = {
        "sections": [
            {
                "id": "s1",
                "columns": [
                    {
                        "id": "c1",
                        "width": 12,
                        "widgets": [
                            {"type": "heading", "props": {"text": "Welcome", "level": 1}},
                            {"type": "text", "props": {"text": "Hello world"}},
                        ],
                    }
                ],
            }
        ]
    }
    out = render_site_html(tree, "My Site")
    assert "<!doctype html>" in out
    assert "<title>My Site</title>" in out
    assert "<h1>Welcome</h1>" in out
    assert "<p>Hello world</p>" in out
    assert "sb-section" in out


def test_render_site_html_custom_title():
    tree = {"title": "Custom Title", "sections": []}
    out = render_site_html(tree, "Ignored")
    assert "<title>Custom Title</title>" in out


def test_render_site_html_escapes_title():
    out = render_site_html({"title": "<script>alert(1)</script>", "sections": []}, "Ignored")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "<script>alert(1)</script>" not in out

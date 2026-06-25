import pytest
from fastapi.responses import HTMLResponse

from pit_panel.web import render


def test_render_with_context(tmp_path, monkeypatch):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    test_template = templates_dir / "test.html"
    test_template.write_text("Hello, {{ user }}!")

    monkeypatch.setattr(render, "TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr(render, "_templates", None)

    response = render.render("test.html", user="World")

    assert isinstance(response, HTMLResponse)
    assert response.body == b"Hello, World!"


def test_render_template_not_found(tmp_path, monkeypatch):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    monkeypatch.setattr(render, "TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr(render, "_templates", None)

    from jinja2.exceptions import TemplateNotFound

    with pytest.raises(TemplateNotFound):
        render.render("missing.html")


def test_render_no_context(tmp_path, monkeypatch):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    test_template = templates_dir / "test.html"
    test_template.write_text("Hello, World!")

    monkeypatch.setattr(render, "TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr(render, "_templates", None)

    response = render.render("test.html")

    assert isinstance(response, HTMLResponse)
    assert response.body == b"Hello, World!"

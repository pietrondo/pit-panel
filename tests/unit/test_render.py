import pytest
from pit_panel.web import render

def test_render_with_mock_template(tmp_path, monkeypatch):
    # Setup a fake template directory
    d = tmp_path / "templates"
    d.mkdir()
    p = d / "test.html"
    p.write_text("Hello {{ username }}!")

    # Patch the TEMPLATES_DIR and reset _templates cache
    monkeypatch.setattr(render, "TEMPLATES_DIR", d)
    monkeypatch.setattr(render, "_templates", None)

    # Call render
    response = render.render("test.html", username="World")

    # Assertions
    assert response.status_code == 200
    assert response.body == b"Hello World!"
    assert response.media_type == "text/html"

def test_render_template_not_found(tmp_path, monkeypatch):
    # Setup a fake empty template directory
    d = tmp_path / "templates"
    d.mkdir()

    monkeypatch.setattr(render, "TEMPLATES_DIR", d)
    monkeypatch.setattr(render, "_templates", None)

    from jinja2.exceptions import TemplateNotFound

    with pytest.raises(TemplateNotFound):
        render.render("missing.html")

def test_get_templates_caching(tmp_path, monkeypatch):
    d = tmp_path / "templates"
    d.mkdir()

    monkeypatch.setattr(render, "TEMPLATES_DIR", d)
    monkeypatch.setattr(render, "_templates", None)

    # First call initializes the cache
    env1 = render._get_templates()

    # Second call returns the cached instance
    env2 = render._get_templates()

    assert env1 is env2

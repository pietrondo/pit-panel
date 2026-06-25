import pytest
from fastapi.responses import HTMLResponse
from jinja2 import Environment

from pit_panel.web import render


@pytest.fixture(autouse=True)
def reset_templates():
    # Reset the global variable before and after each test
    render._templates = None
    yield
    render._templates = None


def test_get_templates(monkeypatch, tmp_path):
    # Mock TEMPLATES_DIR to a temporary directory
    monkeypatch.setattr(render, "TEMPLATES_DIR", tmp_path)

    env = render._get_templates()

    assert isinstance(env, Environment)
    assert env.autoescape is True

    # Second call should return the exact same instance
    env2 = render._get_templates()
    assert env is env2


def test_render(monkeypatch, tmp_path):
    # Mock TEMPLATES_DIR to a temporary directory
    monkeypatch.setattr(render, "TEMPLATES_DIR", tmp_path)

    # Create a dummy template
    template_file = tmp_path / "dummy.html"
    template_file.write_text("<h1>Hello {{ title }}</h1>")

    # Render it
    response = render.render("dummy.html", title="World")

    assert isinstance(response, HTMLResponse)
    assert response.body == b"<h1>Hello World</h1>"

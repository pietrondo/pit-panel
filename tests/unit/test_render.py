import pytest
from fastapi.responses import HTMLResponse
from jinja2 import Environment

from pit_panel.web import render as render_module
from pit_panel.web.render import _get_templates, render


@pytest.fixture(autouse=True)
def reset_templates():
    """Reset the global _templates before and after each test."""
    render_module._templates = None
    yield
    render_module._templates = None


def test_get_templates_memoization():
    """Test that _get_templates initializes the Jinja Environment and caches it."""
    # First call initializes
    env1 = _get_templates()
    assert isinstance(env1, Environment)

    # Second call returns the exact same instance
    env2 = _get_templates()
    assert env1 is env2


def test_render(monkeypatch, tmp_path):
    """Test that render returns an HTMLResponse with correctly rendered template."""
    # Create a mock template
    template_content = "Hello {{ my_name }}!"
    test_template_path = tmp_path / "test.html"
    test_template_path.write_text(template_content)

    # Mock the TEMPLATES_DIR to point to our temp directory
    monkeypatch.setattr(render_module, "TEMPLATES_DIR", tmp_path)

    # render should use the tmp_path templates dir and find test.html
    response = render("test.html", my_name="World")

    assert isinstance(response, HTMLResponse)
    assert response.body == b"Hello World!"

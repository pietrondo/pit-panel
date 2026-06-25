import pytest
from pathlib import Path
from fastapi.responses import HTMLResponse

import pit_panel.web.render as render_module
from pit_panel.web.render import _get_templates, render

@pytest.fixture(autouse=True)
def reset_templates():
    """Reset the global _templates before and after each test."""
    render_module._templates = None
    yield
    render_module._templates = None

def test_get_templates_singleton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(render_module, "TEMPLATES_DIR", tmp_path)

    env1 = _get_templates()
    env2 = _get_templates()

    # Should be the exact same instance
    assert env1 is env2

    # Check autoescape is enabled
    assert env1.autoescape is True

def test_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(render_module, "TEMPLATES_DIR", tmp_path)

    # Create a mock template
    template_file = tmp_path / "test.html"
    template_file.write_text("<h1>Hello {{ user }}</h1>")

    response = render("test.html", user="Jules")

    assert isinstance(response, HTMLResponse)
    assert response.body.decode("utf-8") == "<h1>Hello Jules</h1>"

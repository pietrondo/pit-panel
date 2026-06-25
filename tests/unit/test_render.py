import pytest
from fastapi.responses import HTMLResponse
from jinja2 import Environment

import pit_panel.web.render as render_module


@pytest.fixture
def mock_templates_dir(tmp_path, monkeypatch):
    """Fixture to set up a mock TEMPLATES_DIR and reset the _templates singleton."""
    monkeypatch.setattr(render_module, "TEMPLATES_DIR", tmp_path)

    # Reset singleton before test
    original_templates = render_module._templates
    render_module._templates = None

    # Create a test template
    template_path = tmp_path / "test.html"
    template_path.write_text("<h1>Hello {{ user }}</h1>")

    yield tmp_path

    # Reset singleton after test
    render_module._templates = original_templates


def test_get_templates(mock_templates_dir):
    """Test that _get_templates creates and returns a Jinja2 Environment."""
    env = render_module._get_templates()
    assert isinstance(env, Environment)
    assert env.autoescape is True

    # Test that it loads the mock template
    template = env.get_template("test.html")
    assert template.render(user="World") == "<h1>Hello World</h1>"

    # Test singleton behavior
    env2 = render_module._get_templates()
    assert env is env2


def test_render(mock_templates_dir):
    """Test that render returns an HTMLResponse with correctly rendered content."""
    response = render_module.render("test.html", user="Tester")

    assert isinstance(response, HTMLResponse)
    assert response.body == b"<h1>Hello Tester</h1>"
    assert response.status_code == 200

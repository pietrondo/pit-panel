"""Render utility for Jinja2 templates."""

from typing import Any, cast
from pathlib import Path

from fastapi.responses import HTMLResponse

TEMPLATES_DIR = Path(__file__).parent / "templates"

_templates = None


def _get_templates() -> Any:
    from jinja2 import Environment
    global _templates
    if _templates is None:
        from jinja2 import Environment, FileSystemLoader

        _templates = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return _templates


def render(name: str, **ctx: Any) -> HTMLResponse:
    return HTMLResponse(_get_templates().get_template(name).render(**ctx))

"""Render utility for Jinja2 templates."""

from pathlib import Path
from typing import Any

from fastapi.responses import HTMLResponse
from jinja2 import Environment

TEMPLATES_DIR = Path(__file__).parent / "templates"

_templates = None


def _get_templates() -> Environment:
    global _templates
    if _templates is None:
        from jinja2 import Environment, FileSystemLoader

        _templates = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return _templates


def render(name: str, **ctx: Any) -> HTMLResponse:
    return HTMLResponse(_get_templates().get_template(name).render(**ctx))

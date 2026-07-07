from . import main, ops, wordpress  # noqa: F401 — registers routes on router
from .router import router as router

__all__ = ["router"]

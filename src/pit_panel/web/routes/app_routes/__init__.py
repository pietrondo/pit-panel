from . import (  # noqa: F401 — registers routes on router
    deploy,
    main,
    ops,
    ops_files,
    ops_terminal,
    wordpress,
)
from .router import router as router

__all__ = ["router"]

from .app_routes import router as apps_router
from .auth_routes import router as auth_router
from .containers import router as containers_router
from .dashboard import router as dashboard_router
from .debug import router as debug_router
from .debug_api import router as debug_api_router
from .file_manager import router as file_manager_router
from .logs import router as logs_router
from .security import router as security_router
from .settings import router as settings_router
from .ssl import router as ssl_router
from .subdomains import router as subdomains_router
from .system import router as system_router
from .system_manage import router as system_manage_router

__all__ = [
    "apps_router",
    "auth_router",
    "containers_router",
    "dashboard_router",
    "debug_router",
    "debug_api_router",
    "file_manager_router",
    "logs_router",
    "security_router",
    "settings_router",
    "ssl_router",
    "subdomains_router",
    "system_router",
    "system_manage_router",
]

from fastapi import HTTPException

from pit_panel.config import get_settings
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token, validate_session


def can_access_subdomain(user, subdomain) -> bool:
    if bool(getattr(user, "is_admin", False)):
        return True
    return getattr(subdomain, "owner_user_id", None) == user.id


def require_subdomain_access(user, subdomain):
    if not can_access_subdomain(user, subdomain):
        raise HTTPException(status_code=403, detail="You do not own this subdomain")
    if getattr(subdomain, "is_main_domain", False) and not bool(
        getattr(user, "is_admin", False)
    ):
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return subdomain


async def get_websocket_user(websocket, db):
    cookie = websocket.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    settings = get_settings()
    data = unsign_session_token(settings, cookie)
    if not data or data.get("uid") is None:
        return None
    return await validate_session(db, cookie, settings, data["uid"], data=data)

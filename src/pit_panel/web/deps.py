from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import Settings, get_settings
from pit_panel.db.models import User
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token, validate_session


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie is None:
        raise _unauthorized()

    data = (
        __import__("itsdangerous")
        .URLSafeTimedSerializer(settings.secret_key, salt="pitpanel-session")
        .loads(cookie)
    )

    user = await validate_session(db, cookie, settings, data.get("uid", 0))
    if user is None:
        raise _unauthorized()
    return user


def _unauthorized():
    from fastapi import HTTPException

    return HTTPException(status_code=401, detail="Not authenticated")


def get_settings():
    return Settings()


async def get_optional_user(request: Request, db: AsyncSession) -> User | None:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    data = unsign_session_token(settings, cookie)
    if not data:
        return None
    result = await db.execute(select(User).where(User.id == data.get("uid")))
    return result.scalar_one_or_none()

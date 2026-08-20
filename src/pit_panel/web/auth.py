import datetime
import secrets
import time
from typing import Any, cast

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from pit_panel.config import Settings
from pit_panel.db.models import Session as DBSession
from pit_panel.db.models import User
from pit_panel.security.crypto import hash_token

SESSION_COOKIE = "pitpanel_session"

_serializer_cache: URLSafeTimedSerializer | None = None


def get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    """
    Creates and returns a URLSafeTimedSerializer using the application settings.

    This serializer is used for securely signing and unsigning session tokens
    to prevent tampering and verify expiration.
    """
    global _serializer_cache
    if _serializer_cache is None:
        _serializer_cache = URLSafeTimedSerializer(
            settings.secret_key,
            salt="pitpanel-session",
        )
    return _serializer_cache


def create_session_token(
    settings: Settings, user_id: int, session_id: int, raw: str | None = None
) -> tuple[str, str]:
    """
    Generates a new raw session token and its signed counterpart.

    The signed token encodes the user ID, session ID, and a hash of the raw token.
    This ensures that the token is bound to a specific session and user.
    """
    serializer = get_serializer(settings)
    if raw is None:
        raw = secrets.token_urlsafe(64)
    data = {
        "uid": user_id,
        "sid": session_id,
        "tok": hash_token(raw),
    }
    signed = serializer.dumps(data)
    return raw, signed


def unsign_session_token(settings: Settings, cookie_value: str) -> dict[str, Any] | None:
    serializer = get_serializer(settings)
    try:
        data = serializer.loads(cookie_value, max_age=settings.session_duration_hours * 3600)
        return cast(dict[str, Any], data)
    except (BadSignature, SignatureExpired):
        return None



_SESSION_CACHE: dict[str, tuple[float, Any]] = {}
_SESSION_CACHE_MAX_SIZE = 1000
_SESSION_CACHE_TTL = 30.0

async def validate_session(
    db_session: Any,
    cookie_value: str,
    settings: Settings,
    user_id: int,
    data: dict[str, Any] | None = None,
) -> User | None:
    from sqlalchemy import select

    if data is None:
        data = unsign_session_token(settings, cookie_value)
    if data is None:
        return None

    token_hash = data.get("tok")
    session_id = data.get("sid")

    now = time.monotonic()
    cache_key = f"{session_id}:{token_hash}:{user_id}"
    if cache_key in _SESSION_CACHE:
        cached_at, cached_is_valid = _SESSION_CACHE[cache_key]
        if now - cached_at < _SESSION_CACHE_TTL:
            if not cached_is_valid:
                return None
            # Fetch user quickly without joining session, since we know session is valid via cache
            result = await db_session.execute(select(User).where(User.id == user_id))
            return cast(User | None, result.scalar_one_or_none())

    result = await db_session.execute(
        select(User)
        .join(DBSession, User.id == DBSession.user_id)
        .where(
            DBSession.id == session_id,
            DBSession.token_hash == token_hash,
            DBSession.user_id == user_id,
            DBSession.expires_at > datetime.datetime.now(datetime.UTC),
        )
    )
    user = result.scalar_one_or_none()

    if len(_SESSION_CACHE) >= _SESSION_CACHE_MAX_SIZE:
        _SESSION_CACHE.clear()

    _SESSION_CACHE[cache_key] = (now, user is not None)
    return cast(User | None, user)


async def create_session_record(
    db_session: Any,
    user_id: int,
    token_hash: str,
    ip: str | None,
    user_agent: str | None,
    settings: Settings,
) -> int:
    expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=settings.session_duration_hours
    )
    sess = DBSession(
        user_id=user_id,
        token_hash=token_hash,
        ip=ip,
        user_agent=user_agent,
        expires_at=expires,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)
    return cast(int, sess.id)


async def revoke_session(db_session: Any, session_id: int) -> None:
    from sqlalchemy import delete

    # Clear cache entries matching this session
    keys_to_delete = [k for k in _SESSION_CACHE if k.startswith(f"{session_id}:")]
    for k in keys_to_delete:
        del _SESSION_CACHE[k]
    await db_session.execute(delete(DBSession).where(DBSession.id == session_id))
    await db_session.commit()

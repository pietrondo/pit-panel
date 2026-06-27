import datetime
import secrets
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from pit_panel.config import Settings
from pit_panel.db.models import Session as DBSession
from pit_panel.db.models import User
from pit_panel.security.crypto import hash_token

SESSION_COOKIE = "pitpanel_session"


def get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    """
    Creates and returns a URLSafeTimedSerializer using the application settings.

    This serializer is used for securely signing and unsigning session tokens
    to prevent tampering and verify expiration.
    """
    return URLSafeTimedSerializer(
        settings.secret_key,
        salt="pitpanel-session",
    )


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
        return data
    except (BadSignature, SignatureExpired):
        return None


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
    return result.scalar_one_or_none()


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
    return sess.id


async def revoke_session(db_session: Any, session_id: int) -> None:
    from sqlalchemy import delete

    await db_session.execute(delete(DBSession).where(DBSession.id == session_id))
    await db_session.commit()

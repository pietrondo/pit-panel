from typing import Any

import pytest


class TestSessionAuth:
    def test_get_serializer(self, settings):
        from itsdangerous import URLSafeTimedSerializer

        from pit_panel.web.auth import get_serializer

        serializer = get_serializer(settings)
        assert isinstance(serializer, URLSafeTimedSerializer)

        # itsdangerous stores secret_key as a byte string if passed as string
        expected_secret = (
            settings.secret_key.encode()
            if isinstance(settings.secret_key, str)
            else settings.secret_key
        )
        assert serializer.secret_key == expected_secret

        expected_salt = (
            b"pitpanel-session" if isinstance(serializer.salt, bytes) else "pitpanel-session"
        )
        assert serializer.salt == expected_salt

    def test_create_and_verify_token(self, settings):
        from pit_panel.web.auth import create_session_token, unsign_session_token

        raw, signed = create_session_token(settings, user_id=1, session_id=42)
        assert raw
        assert signed

        data = unsign_session_token(settings, signed)
        assert data is not None
        assert data["uid"] == 1
        assert data["sid"] == 42

    def test_invalid_token_rejected(self, settings):
        from pit_panel.web.auth import unsign_session_token

        assert unsign_session_token(settings, "garbage") is None

    def test_token_hash_consistency(self, settings):
        from pit_panel.security.crypto import hash_token
        from pit_panel.web.auth import create_session_token, unsign_session_token

        raw, signed = create_session_token(settings, user_id=1, session_id=1)
        data = unsign_session_token(settings, signed)
        assert data["tok"] == hash_token(raw)

    @pytest.mark.asyncio
    async def test_validate_session(self, settings: Any) -> None:
        import datetime
        import secrets

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base, User
        from pit_panel.db.models import Session as DBSession
        from pit_panel.security.crypto import hash_token
        from pit_panel.web.auth import create_session_record, create_session_token, revoke_session, validate_session

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db_session:
            user = User(
                username="testuser", email="test@test.com", password_hash="hash", is_admin=True
            )
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            raw = secrets.token_urlsafe(64)
            token_hash = hash_token(raw)
            session_id = await create_session_record(
                db_session,
                user_id=user.id,
                token_hash=token_hash,
                ip="127.0.0.1",
                user_agent="pytest",
                settings=settings,
            )

            _, signed = create_session_token(
                settings, user_id=user.id, session_id=session_id, raw=raw
            )

            valid_user = await validate_session(db_session, signed, settings, user.id)
            assert valid_user is not None
            assert valid_user.id == user.id

            invalid_result = await validate_session(
                db_session, "invalid_cookie_value", settings, user.id
            )
            assert invalid_result is None

            wrong_user_result = await validate_session(db_session, signed, settings, user.id + 1)
            assert wrong_user_result is None

            await revoke_session(db_session, session_id)
            revoked_result = await validate_session(db_session, signed, settings, user.id)
            assert revoked_result is None

            session_id_2 = await create_session_record(
                db_session,
                user_id=user.id,
                token_hash=token_hash,
                ip="127.0.0.1",
                user_agent="pytest",
                settings=settings,
            )
            _, signed_2 = create_session_token(
                settings, user_id=user.id, session_id=session_id_2, raw=raw
            )

            db_sess = await db_session.get(DBSession, session_id_2)
            if db_sess:
                db_sess.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
                    hours=1
                )
            await db_session.commit()

            expired_result = await validate_session(db_session, signed_2, settings, user.id)
            assert expired_result is None

    @pytest.mark.asyncio
    async def test_revoke_session(self, settings):
        import datetime

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base, User
        from pit_panel.db.models import Session as DBSession
        from pit_panel.web.auth import revoke_session

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            user = User(
                username="test_revoke",
                email="test_revoke@test.com",
                password_hash="hash",
                is_admin=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            sess = DBSession(
                user_id=user.id,
                token_hash="testhash123",
                ip="127.0.0.1",
                expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
            )
            db.add(sess)
            await db.commit()
            await db.refresh(sess)

            result = await db.execute(select(DBSession).where(DBSession.id == sess.id))
            assert result.scalar_one_or_none() is not None

            await revoke_session(db, sess.id)

            result = await db.execute(select(DBSession).where(DBSession.id == sess.id))
            assert result.scalar_one_or_none() is None


class TestAppFactory:
    def test_create_app(self, settings):
        from pit_panel.web.app import create_app

        app = create_app(settings)
        assert app.title == "pit-panel"

    def test_app_health_endpoint(self, settings, monkeypatch):
        import tempfile

        from fastapi.testclient import TestClient

        from pit_panel.config import Settings, init_settings
        from pit_panel.web.app import create_app

        tmpdir = tempfile.mkdtemp()
        settings = Settings(secret_key="test", database_url=f"sqlite+aiosqlite:///{tmpdir}/test.db")
        init_settings()
        monkeypatch.setattr("pit_panel.config._settings", settings)
        app = create_app(settings)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSessionRecords:
    @pytest.mark.asyncio
    async def test_create_session_record(self, settings):
        import datetime

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base, User
        from pit_panel.db.models import Session as DBSession
        from pit_panel.web.auth import create_session_record

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            user = User(
                username="test_user", email="test@test.com", password_hash="hash", is_admin=False
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            token_hash = "fake_token_hash"
            ip = "127.0.0.1"
            user_agent = "pytest-agent"

            sess_id = await create_session_record(
                db_session=db,
                user_id=user.id,
                token_hash=token_hash,
                ip=ip,
                user_agent=user_agent,
                settings=settings,
            )

            assert sess_id is not None
            assert sess_id > 0

            # Verify the record was created
            from sqlalchemy import select

            result = await db.execute(select(DBSession).where(DBSession.id == sess_id))
            sess = result.scalar_one_or_none()

            assert sess is not None
            assert sess.user_id == user.id
            assert sess.token_hash == token_hash
            assert sess.ip == ip
            assert sess.user_agent == user_agent
            assert isinstance(sess.expires_at, datetime.datetime)

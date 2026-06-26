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
    async def test_validate_session_invalid_cookie(self, settings):
        from pit_panel.web.auth import validate_session

        # Passing an invalid cookie should return None immediately
        user = await validate_session(
            db_session=None, cookie_value="invalid-cookie-data", settings=settings, user_id=1
        )
        assert user is None

    @pytest.mark.asyncio
    async def test_validate_session_not_found(self, settings):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base
        from pit_panel.web.auth import create_session_token, validate_session

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            # Generate a valid token, but don't insert a corresponding Session in the DB
            raw, signed = create_session_token(settings, user_id=1, session_id=999)

            user = await validate_session(
                db_session=db, cookie_value=signed, settings=settings, user_id=1
            )
            assert user is None

    @pytest.mark.asyncio
    async def test_validate_session_expired(self, settings):
        import datetime

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base
        from pit_panel.db.models import Session as DBSession
        from pit_panel.security.crypto import hash_token
        from pit_panel.web.auth import create_session_token, validate_session

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            raw, signed = create_session_token(settings, user_id=1, session_id=1)

            # Insert an expired session
            past_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
            db_sess = DBSession(id=1, user_id=1, token_hash=hash_token(raw), expires_at=past_time)
            db.add(db_sess)
            await db.commit()

            user = await validate_session(
                db_session=db, cookie_value=signed, settings=settings, user_id=1
            )
            assert user is None

    @pytest.mark.asyncio
    async def test_validate_session_user_not_found(self, settings):
        import datetime

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base
        from pit_panel.db.models import Session as DBSession
        from pit_panel.security.crypto import hash_token
        from pit_panel.web.auth import create_session_token, validate_session

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            raw, signed = create_session_token(settings, user_id=1, session_id=1)

            # Insert a valid session, but no User
            future_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
            db_sess = DBSession(id=1, user_id=1, token_hash=hash_token(raw), expires_at=future_time)
            db.add(db_sess)
            await db.commit()

            user = await validate_session(
                db_session=db, cookie_value=signed, settings=settings, user_id=1
            )
            assert user is None

    @pytest.mark.asyncio
    async def test_validate_session_success(self, settings):
        import datetime

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base, User
        from pit_panel.db.models import Session as DBSession
        from pit_panel.security.crypto import hash_token
        from pit_panel.web.auth import create_session_token, validate_session

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            # Create user
            test_user = User(
                id=1, username="test_user", email="test@example.com", password_hash="dummy"
            )
            db.add(test_user)
            await db.flush()

            raw, signed = create_session_token(settings, user_id=test_user.id, session_id=1)

            # Create session
            future_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
            db_sess = DBSession(
                id=1, user_id=test_user.id, token_hash=hash_token(raw), expires_at=future_time
            )
            db.add(db_sess)
            await db.commit()

            user = await validate_session(
                db_session=db, cookie_value=signed, settings=settings, user_id=test_user.id
            )
            assert user is not None
            assert user.id == test_user.id
            assert user.username == "test_user"


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

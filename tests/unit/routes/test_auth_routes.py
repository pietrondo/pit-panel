from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import User
from pit_panel.db.session import get_db
from pit_panel.web.app import create_app


@pytest.fixture
def app_settings(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)
    monkeypatch.setattr("pit_panel.db.session._engine", None)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", None)
    return s


@pytest.fixture
def client(app_settings):
    app = create_app(app_settings)
    return TestClient(app)


def _make_user(**kwargs):
    defaults = {
        "id": 1,
        "username": "admin",
        "email": "admin@test.com",
        "password_hash": "hashed",
        "totp_enabled": False,
        "totp_secret": None,
    }
    defaults.update(kwargs)
    return User(**defaults)


async def _seed_user(db_session, **kwargs):
    user = _make_user(**kwargs)
    db_session.add(user)
    await db_session.commit()
    return user


class TestLoginPage:
    def test_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "pit-panel" in resp.text

    def test_login_page_redirects_if_authenticated(self, client):
        from pit_panel.web.auth import create_session_token

        s = Settings(
            secret_key="test-secret-key-32chars!!",
            database_url="sqlite+aiosqlite://",
            debug=True,
        )
        _, cookie = create_session_token(s, 1, 1)
        resp = client.get("/login", cookies={"pitpanel_session": cookie}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"


class TestLoginPost:
    @pytest.fixture(autouse=True)
    def _patch_notifiers(self, monkeypatch):
        monkeypatch.setattr("pit_panel.core.notifier.notify_login_failed", AsyncMock())
        monkeypatch.setattr("pit_panel.core.notifier.notify_login_success", AsyncMock())

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client, db_session):
        import bcrypt

        pw_hash = bcrypt.hashpw(b"the_actual_db_password", bcrypt.gensalt())
        await _seed_user(db_session, password_hash=pw_hash.decode())

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        resp = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert resp.status_code == 200
        assert "Invalid credentials" in resp.text

    @pytest.mark.asyncio
    async def test_login_valid_credentials_no_totp(self, client, db_session):
        import bcrypt

        pw_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt())
        await _seed_user(db_session, password_hash=pw_hash.decode())

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        with patch("pit_panel.web.routes.auth_routes.create_session_token") as mock_token:
            mock_token.return_value = ("raw-token", "signed-cookie")
            with patch(
                "pit_panel.web.routes.auth_routes.create_session_record",
                new_callable=AsyncMock,
            ) as mock_record:
                mock_record.return_value = 42
                with patch("pit_panel.web.routes.auth_routes.unsign_session_token") as mock_unsign:
                    mock_unsign.return_value = {"tok": "hashed-token"}
                    resp = client.post(
                        "/login",
                        data={"username": "admin", "password": "correct"},
                        follow_redirects=False,
                    )
                    assert resp.status_code == 302
                    assert resp.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_login_totp_required(self, client, db_session):
        import bcrypt

        pw_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt())
        await _seed_user(
            db_session,
            password_hash=pw_hash.decode(),
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        resp = client.post("/login", data={"username": "admin", "password": "correct"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_login_totp_invalid_code(self, client, db_session):
        import bcrypt

        pw_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt())
        await _seed_user(
            db_session,
            password_hash=pw_hash.decode(),
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        with patch("pit_panel.web.routes.auth_routes.verify_totp") as mock_verify:
            mock_verify.return_value = False
            resp = client.post(
                "/login",
                data={"username": "admin", "password": "correct", "totp_code": "000000"},
            )
            assert resp.status_code == 200
            assert "Invalid TOTP" in resp.text

    @pytest.mark.asyncio
    async def test_login_valid_totp(self, client, db_session):
        import bcrypt

        pw_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt())
        await _seed_user(
            db_session,
            id=2,
            username="admin2",
            email="admin2@test.com",
            password_hash=pw_hash.decode(),
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        with patch("pit_panel.web.routes.auth_routes.verify_totp") as mock_verify:
            mock_verify.return_value = True
            with patch("pit_panel.web.routes.auth_routes.create_session_token") as mock_token:
                mock_token.return_value = ("raw-token", "signed-cookie")
                with patch(
                    "pit_panel.web.routes.auth_routes.create_session_record",
                    new_callable=AsyncMock,
                ) as mock_record:
                    mock_record.return_value = 99
                    with patch(
                        "pit_panel.web.routes.auth_routes.unsign_session_token"
                    ) as mock_unsign:
                        mock_unsign.return_value = {"tok": "hashed-token"}
                        resp = client.post(
                            "/login",
                            data={
                                "username": "admin2",
                                "password": "correct",
                                "totp_code": "123456",
                            },
                            follow_redirects=False,
                        )
                        assert resp.status_code == 302
                        assert resp.headers["location"] == "/"


class TestLogout:
    def test_logout_no_cookie(self, client):
        resp = client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_logout_with_invalid_cookie(self, client):
        from pit_panel.web.auth import SESSION_COOKIE

        resp = client.get(
            "/logout",
            cookies={SESSION_COOKIE: "invalid-cookie-value"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    def test_logout_with_valid_session(self, client, app_settings, db_session):
        from pit_panel.web.auth import SESSION_COOKIE, create_session_token

        _, cookie = create_session_token(app_settings, 1, 1)

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        with patch("pit_panel.web.routes.auth_routes.unsign_session_token") as mock_unsign:
            mock_unsign.return_value = {"sid": 1, "uid": 1, "tok": "hash"}
            with patch("pit_panel.web.routes.auth_routes.revoke_session", new_callable=AsyncMock):
                resp = client.get(
                    "/logout",
                    cookies={SESSION_COOKIE: cookie},
                    follow_redirects=False,
                )
            assert resp.status_code == 302
            assert resp.headers["location"] == "/login"


class TestSetup2FA:
    def test_setup_2fa_unauthenticated(self, client):
        resp = client.get("/setup-2fa", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login"

    @pytest.mark.asyncio
    async def test_setup_2fa_authenticated(self, client, app_settings, db_session):
        from pit_panel.web.auth import SESSION_COOKIE, create_session_token

        _, cookie = create_session_token(app_settings, 1, 1)

        await _seed_user(db_session, totp_enabled=False, totp_secret="JBSWY3DPEHPK3PXP")

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        with patch("pit_panel.web.routes.auth_routes.get_user") as mock_get_user:
            mock_get_user.return_value = _make_user(totp_secret="JBSWY3DPEHPK3PXP")
            resp = client.get("/setup-2fa", cookies={SESSION_COOKIE: cookie})
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_setup_2fa_enable_invalid_code(self, client, app_settings, db_session):
        from pit_panel.web.auth import SESSION_COOKIE, create_session_token

        _, cookie = create_session_token(app_settings, 1, 1)

        mock_user = _make_user(totp_enabled=False, totp_secret="JBSWY3DPEHPK3PXP")
        await _seed_user(db_session, totp_enabled=False, totp_secret="JBSWY3DPEHPK3PXP")

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        with patch("pit_panel.web.routes.auth_routes.get_user") as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch("pit_panel.web.routes.auth_routes.verify_totp") as mock_verify:
                mock_verify.return_value = False
                resp = client.post(
                    "/setup-2fa",
                    data={"code": "000000"},
                    cookies={SESSION_COOKIE: cookie},
                )
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_setup_2fa_enable_success(self, client, app_settings, db_session):
        from pit_panel.web.auth import SESSION_COOKIE, create_session_token

        _, cookie = create_session_token(app_settings, 1, 1)

        mock_user = _make_user(totp_enabled=False, totp_secret="JBSWY3DPEHPK3PXP")
        await _seed_user(db_session, totp_enabled=False, totp_secret="JBSWY3DPEHPK3PXP")

        async def _override():
            yield db_session

        client.app.dependency_overrides[get_db] = _override

        with patch("pit_panel.web.routes.auth_routes.get_user") as mock_get_user:
            mock_get_user.return_value = mock_user
            with patch("pit_panel.web.routes.auth_routes.verify_totp") as mock_verify:
                mock_verify.return_value = True
                resp = client.post(
                    "/setup-2fa",
                    data={"code": "123456"},
                    cookies={SESSION_COOKIE: cookie},
                    follow_redirects=False,
                )
                assert resp.status_code == 302
                assert resp.headers["location"] == "/"

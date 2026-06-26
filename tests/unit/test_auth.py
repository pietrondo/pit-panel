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

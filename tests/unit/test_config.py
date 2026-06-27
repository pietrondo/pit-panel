import tempfile
from pathlib import Path


class TestSettings:
    def test_defaults(self):
        from pit_panel.config import Settings

        s = Settings(secret_key="test")
        assert s.host == "127.0.0.1"
        assert s.port == 8080
        assert s.debug is False
        assert s.session_duration_hours == 24

    def test_database_url_default(self):
        from pit_panel.config import Settings

        s = Settings(data_dir="/tmp/test", database_url="")
        url = s.get_database_url()
        assert "sqlite+aiosqlite://" in url
        assert "/tmp/test/pit-panel.db" in url

    def test_database_url_custom(self):
        from pit_panel.config import Settings

        s = Settings(database_url="sqlite+aiosqlite:///custom.db")
        assert s.get_database_url() == "sqlite+aiosqlite:///custom.db"

    def test_from_config_file(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write('host = "0.0.0.0"\nport = 9999\nsecret_key = "fromfile"\n')
            path = f.name

        try:
            from pit_panel.config import Settings

            s = Settings.from_config_file(path)
            assert s.host == "0.0.0.0"
            assert s.port == 9999
            assert s.secret_key == "fromfile"
        finally:
            Path(path).unlink()

    def test_get_settings_singleton(self):
        from pit_panel.config import get_settings, init_settings

        s1 = init_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_effective_domain_and_panel_url_with_base_domain(self):
        from pit_panel.config import Settings

        s = Settings(base_domain="example.com", panel_subdomain="admin")
        assert s.effective_domain == "example.com"
        assert s.panel_url == "https://admin.example.com"

    def test_effective_domain_and_panel_url_without_base_domain(self, monkeypatch):
        from pit_panel.config import Settings

        # Mock _detect_ip to return a fixed IP
        monkeypatch.setattr(Settings, "_detect_ip", staticmethod(lambda: "192.168.1.100"))

        s = Settings(base_domain="", panel_subdomain="panel")
        assert s.effective_domain == "192-168-1-100.nip.io"
        assert s.panel_url == "https://panel.192-168-1-100.nip.io"

    def test_detect_ip_success(self, monkeypatch):
        from pit_panel.config import Settings

        class MockResponse:
            text = "203.0.113.50\n"

        def mock_get(*args, **kwargs):
            return MockResponse()

        monkeypatch.setattr("httpx.get", mock_get)
        assert Settings._detect_ip() == "203.0.113.50"

    def test_detect_ip_exception(self, monkeypatch):
        from pit_panel.config import Settings

        def mock_get(*args, **kwargs):
            raise Exception("Connection failed")

        monkeypatch.setattr("httpx.get", mock_get)
        assert Settings._detect_ip() == "127.0.0.1"

    def test_ensure_paths(self, monkeypatch):
        from pathlib import Path

        from pit_panel.config import Settings

        s = Settings(data_dir="/fake/data", apps_dir="/fake/apps")

        called_paths = []

        def mock_mkdir(self_path, parents=False, exist_ok=False):
            assert parents is True
            assert exist_ok is True
            called_paths.append(str(self_path))

        monkeypatch.setattr(Path, "mkdir", mock_mkdir)

        s.ensure_paths()

        assert "/fake/data" in called_paths
        assert "/fake/apps" in called_paths
        assert len(called_paths) == 2

    def test_effective_domain_explicit(self):
        from pit_panel.config import Settings

        s1 = Settings(base_domain="mydomain.com")
        assert s1.effective_domain == "mydomain.com"

        s2 = Settings(base_domain="")
        assert "nip.io" in s2.effective_domain

    def test_get_settings_none(self):
        import pit_panel.config
        from pit_panel.config import get_settings

        # Reset the global to force initialization
        pit_panel.config._settings = None
        s = get_settings()
        assert s is not None

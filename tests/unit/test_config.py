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
        from pit_panel.config import Settings, get_settings, init_settings

        s1 = init_settings()
        s2 = get_settings()
        assert s1 is s2

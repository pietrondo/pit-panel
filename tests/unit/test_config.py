import tempfile
import pytest
from pathlib import Path


from typing import Any

class TestSettings:
    def test_defaults(self) -> None:
        from pit_panel.config import Settings

        s = Settings(secret_key="test")
        assert s.host == "127.0.0.1"
        assert s.port == 8080
        assert s.debug is False
        assert s.session_duration_hours == 24

    def test_database_url_default(self) -> None:
        from pit_panel.config import Settings

        s = Settings(data_dir="/tmp/test", database_url="")
        url = s.get_database_url()
        assert "sqlite+aiosqlite://" in url
        assert "/tmp/test/pit-panel.db" in url

    def test_database_url_custom(self) -> None:
        from pit_panel.config import Settings

        s = Settings(database_url="sqlite+aiosqlite:///custom.db")
        assert s.get_database_url() == "sqlite+aiosqlite:///custom.db"

    def test_from_config_file(self) -> None:
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

    def test_get_settings_singleton(self) -> None:
        from pit_panel.config import get_settings, init_settings

        s1 = init_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_effective_domain_and_panel_url_with_base_domain(self) -> None:
        from pit_panel.config import Settings

        s = Settings(base_domain="example.com", panel_subdomain="admin")
        assert s.effective_domain == "example.com"
        assert s.panel_url == "https://admin.example.com"

    def test_effective_domain_and_panel_url_without_base_domain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pit_panel.config import Settings

        # Mock _detect_ip to return a fixed IP
        monkeypatch.setattr(Settings, "_detect_ip", staticmethod(lambda: "192.168.1.100"))

        s = Settings(base_domain="", panel_subdomain="panel")
        assert s.effective_domain == "192-168-1-100.nip.io"
        assert s.panel_url == "https://panel.192-168-1-100.nip.io"

    def test_detect_ip_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pit_panel.config import Settings

        class MockResponse:
            text = "203.0.113.50\n"

        def mock_get(*args: Any, **kwargs: Any) -> Any:
            return MockResponse()

        monkeypatch.setattr("httpx.get", mock_get)
        assert Settings._detect_ip() == "203.0.113.50"

    def test_detect_ip_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pit_panel.config import Settings

        def mock_get(*args: Any, **kwargs: Any) -> Any:
            raise Exception("Connection failed")

        monkeypatch.setattr("httpx.get", mock_get)
        assert Settings._detect_ip() == "127.0.0.1"

    def test_ensure_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pathlib import Path

        from pit_panel.config import Settings

        s = Settings(data_dir="/fake/data", apps_dir="/fake/apps")

        called_paths = []

        def mock_mkdir(self_path: Any, parents: bool = False, exist_ok: bool = False) -> None:
            assert parents is True
            assert exist_ok is True
            called_paths.append(str(self_path))

        monkeypatch.setattr(Path, "mkdir", mock_mkdir)

        s.ensure_paths()

        assert Path("/fake/data") in [Path(p) for p in called_paths]
        assert Path("/fake/apps") in [Path(p) for p in called_paths]
        assert len(called_paths) == 2

    def test_effective_domain_explicit(self) -> None:
        from pit_panel.config import Settings

        s1 = Settings(base_domain="mydomain.com")
        assert s1.effective_domain == "mydomain.com"

        s2 = Settings(base_domain="")
        assert "nip.io" in s2.effective_domain

    def test_get_settings_none(self) -> None:
        import pit_panel.config
        from pit_panel.config import get_settings

        # Reset the global to force initialization
        pit_panel.config._settings = None
        s = get_settings()
        assert s is not None

    def test_panel_url_edge_cases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pit_panel.config import Settings

        # Happy path: explicit domain and subdomain
        s = Settings(base_domain="example.com", panel_subdomain="admin")
        assert s.panel_url == "https://admin.example.com"

        # Edge case: empty panel_subdomain
        s = Settings(base_domain="example.com", panel_subdomain="")
        assert s.panel_url == "https://.example.com"

        # Edge case: nip.io fallback
        monkeypatch.setattr(Settings, "_detect_ip", staticmethod(lambda: "10.0.0.1"))
        s = Settings(base_domain="", panel_subdomain="panel")
        assert s.panel_url == "https://panel.10-0-0-1.nip.io"

    def test_panel_url_explicit_base_domain(self) -> None:
        from pit_panel.config import Settings

        s = Settings(base_domain="test.com", panel_subdomain="mypanel")
        assert s.panel_url == "https://mypanel.test.com"

    def test_panel_url_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pit_panel.config import Settings

        monkeypatch.setattr(Settings, "_detect_ip", staticmethod(lambda: "1.2.3.4"))
        s = Settings()
        assert s.panel_url == "https://panel.1-2-3-4.nip.io"

    def test_save_config_file(self) -> None:
        import tempfile
        import tomllib as tomli
        from pathlib import Path

        from pit_panel.config import Settings

        with tempfile.TemporaryDirectory() as tmpdir:
            s = Settings(data_dir=tmpdir, secret_key="test_save")
            s.save_config_file()

            config_path = Path(tmpdir) / "config.toml"
            assert config_path.exists()

            with open(config_path, "rb") as f:
                data = tomli.load(f)

            assert data["secret_key"] == "test_save"
            assert data["host"] == "127.0.0.1"

    def test_save_config_file_creates_parents(self) -> None:
        import tempfile
        from pathlib import Path

        from pit_panel.config import Settings

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "nested" / "dir"
            s = Settings(data_dir=str(nested_dir), secret_key="test_save_nested")
            s.save_config_file()

            config_path = nested_dir / "config.toml"
            assert config_path.exists()

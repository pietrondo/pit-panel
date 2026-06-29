import tomllib as tomli
from pathlib import Path
from typing import cast

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):  # type: ignore[misc]
    model_config = SettingsConfigDict(env_prefix="PITPANEL_")

    # Paths
    config_path: str = "/etc/pit-panel/config.toml"
    data_dir: str = "/var/lib/pit-panel"
    apps_dir: str = "/opt/pit-panel/apps"

    # Database
    database_url: str = ""

    # Security
    secret_key: str = ""
    session_duration_hours: int = 24
    bcrypt_cost: int = 12
    abuseipdb_api_key: str = ""
    sudo_password: str = ""

    # Server
    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False

    # Caddy
    caddy_admin_url: str = "http://127.0.0.1:2019"
    base_domain: str = ""
    panel_subdomain: str = "panel"
    ssl_auto_renew_days: int = 14

    @property
    def effective_domain(self) -> str:
        if self.base_domain:
            return self.base_domain
        return f"{self._detect_ip().replace('.', '-')}.nip.io"

    @property
    def panel_url(self) -> str:
        """Get the full URL for the panel based on configured domains."""
        return f"https://{self.panel_subdomain}.{self.effective_domain}"

    @staticmethod
    def _detect_ip() -> str:
        try:
            import httpx

            resp = httpx.get("https://api.ipify.org", timeout=3)
            return cast(str, resp.text.strip())
        except Exception:
            return "127.0.0.1"

    # Updates
    git_remote: str = "https://github.com/pietrondo/pit-panel.git"
    git_branch: str = "main"
    auto_update: bool = True
    update_interval_hours: int = 6

    # Docker
    docker_socket: str = "unix:///var/run/docker.sock"

    # Debug API
    debug_token_path: str = "/etc/pit-panel/debug_token"

    # Ratelimit
    rate_limit_login: str = "5/minute"
    rate_limit_api: str = "60/minute"

    @classmethod
    def from_config_file(cls, path: str | None = None) -> "Settings":
        import os
        config_path_str = (
            path
            or os.environ.get("PITPANEL_CONFIG_PATH")
            or "/etc/pit-panel/config.toml"
        )
        config_file = Path(config_path_str)
        if config_file.exists():
            with open(config_file, "rb") as f:
                data = tomli.load(f)
            return cls(**data)
        return cls()

    def ensure_paths(self) -> None:
        for p in [self.data_dir, self.apps_dir]:
            Path(p).mkdir(parents=True, exist_ok=True)

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{self.data_dir}/pit-panel.db"

    def save_config_file(self) -> None:
        import tomli_w
        config_path = Path(self.config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "base_domain": self.base_domain,
            "panel_subdomain": self.panel_subdomain,
            "host": self.host,
            "abuseipdb_api_key": self.abuseipdb_api_key,
            "sudo_password": self.sudo_password,
            "caddy_admin_url": self.caddy_admin_url,
            "secret_key": self.secret_key,
            "database_url": self.database_url,
            "debug": self.debug,
        }
        with open(config_path, "wb") as f:
            tomli_w.dump(data, f)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_config_file()
    return _settings


def init_settings(path: str | None = None) -> Settings:
    global _settings
    _settings = Settings.from_config_file(path)
    return _settings

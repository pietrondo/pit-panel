import yaml
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import os

def _get_db_service_info(compose_path: Path, env_path: Path) -> Optional[Tuple[str, str, str, str, str]]:
    """Return (service_name, db_type, user, password, db_name) from docker-compose.yml and .env."""
    try:
        with open(compose_path) as f:
            data = yaml.safe_load(f)
        if not data or "services" not in data:
            return None

        from dotenv import dotenv_values
        env_vars = dotenv_values(env_path) if env_path.exists() else {}

        for name, svc in data["services"].items():
            image = svc.get("image", "").lower()
            env_config = svc.get("environment", {})
            if isinstance(env_config, list):
                # Convert list to dict
                new_env = {}
                for item in env_config:
                    if '=' in item:
                        k, v = item.split('=', 1)
                        new_env[k] = v
                env_config = new_env

            def resolve_env(key: str) -> str:
                val = env_config.get(key, "")
                if val.startswith("${") and val.endswith("}"):
                    val = val[2:-1]
                    return env_vars.get(val, "")
                if val.startswith("$"):
                    val = val[1:]
                    return env_vars.get(val, "")
                return val

            if "postgres" in image:
                user = resolve_env("POSTGRES_USER")
                password = resolve_env("POSTGRES_PASSWORD")
                db_name = resolve_env("POSTGRES_DB")
                return name, "postgres", user, password, db_name
            elif "mysql" in image or "mariadb" in image:
                user = resolve_env("MYSQL_USER")
                password = resolve_env("MYSQL_PASSWORD")
                db_name = resolve_env("MYSQL_DATABASE")
                # Sometimes root is used instead
                if not user:
                    user = "root"
                    password = resolve_env("MYSQL_ROOT_PASSWORD") or password
                return name, "mysql", user, password, db_name
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

print(_get_db_service_info(Path("templates-app/postgresql/docker-compose.yml.tpl"), Path("nonexistent")))

from pathlib import Path
import yaml

def get_db_info(compose_path: Path) -> tuple[str, str, str] | None:
    """Return (service_name, db_type, user, password, db_name) from docker-compose.yml."""
    try:
        with open(compose_path) as f:
            data = yaml.safe_load(f)
        if not data or "services" not in data:
            return None

        for name, svc in data["services"].items():
            image = svc.get("image", "").lower()
            if "postgres" in image:
                return name, "postgres", svc.get("environment", {})
            elif "mysql" in image or "mariadb" in image:
                return name, "mysql", svc.get("environment", {})
        return None
    except Exception as e:
        print(e)
        return None

print(get_db_info(Path("templates-app/postgresql/docker-compose.yml.tpl")))
print(get_db_info(Path("templates-app/wordpress/docker-compose.yml.tpl")))

from pathlib import Path
import yaml

def _get_db_dump_info(compose_path: Path) -> tuple[str, str] | None:
    """Return (service_name, db_type) from docker-compose.yml.
    db_type can be 'postgres' or 'mysql'.
    """
    try:
        with open(compose_path) as f:
            data = yaml.safe_load(f)
        if not data or "services" not in data:
            return None
        for name, svc in data["services"].items():
            image = svc.get("image", "").lower()
            if "postgres" in image:
                return name, "postgres"
            elif "mysql" in image or "mariadb" in image:
                return name, "mysql"
        return None
    except Exception as e:
        print(f"Error parsing {compose_path}: {e}")
        return None

print(_get_db_dump_info(Path("templates-app/postgresql/docker-compose.yml.tpl")))
print(_get_db_dump_info(Path("templates-app/wordpress/docker-compose.yml.tpl")))

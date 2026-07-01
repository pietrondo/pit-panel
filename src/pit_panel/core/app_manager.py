"""Application deployment from templates."""

import json
import logging
import secrets
import shutil
from pathlib import Path
from string import Template
from typing import Any, cast

TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates-app"
logger = logging.getLogger(__name__)


class AppManager:
    def __init__(self, apps_dir: str = "/opt/pit-panel/apps"):
        self.apps_dir = Path(apps_dir)

    def deploy_template(
        self,
        subdomain: str,
        stack_type: str,
        variables: dict[str, str] | None = None,
    ) -> Path:
        if stack_type not in self.list_templates():
            raise ValueError(f"Invalid stack type: {stack_type}")

        template_dir = TEMPLATES_DIR / stack_type

        target_dir = self.apps_dir / subdomain
        target_dir.mkdir(parents=True, exist_ok=True)

        vars_dict = dict(variables or {})
        vars_dict.setdefault("DB_PASSWORD", secrets.token_urlsafe(24))
        vars_dict.setdefault("DB_USER", "appuser")
        vars_dict.setdefault("DB_NAME", "appdb")
        vars_dict["subdomain"] = subdomain
        if stack_type == "wordpress":
            vars_dict.setdefault("PORT", "8081")
            vars_dict.setdefault("WP_TITLE", "My Blog")
            vars_dict.setdefault("WP_ADMIN_USER", "admin")
            vars_dict.setdefault("WP_ADMIN_PASSWORD", secrets.token_urlsafe(12))
            vars_dict.setdefault("WP_ADMIN_EMAIL", "admin@localhost")
            vars_dict.setdefault("WP_LOCALE", "it_IT")
            vars_dict.setdefault("PMA_PORT", str(int(vars_dict.get("PORT", 8081)) + 1))


        for file_path in template_dir.iterdir():
            if file_path.suffix == ".tpl":
                template = Template(file_path.read_text())
                output = template.safe_substitute(vars_dict)
                output_name = ".env" if file_path.stem == "env" else file_path.stem
                (target_dir / output_name).write_text(output)
            elif file_path.name != "meta.json":
                shutil.copy2(file_path, target_dir / file_path.name)

        return target_dir

    def delete_app(self, subdomain: str) -> bool:
        target_dir = self.apps_dir / subdomain
        if target_dir.exists() and target_dir.is_dir():
            try:
                shutil.rmtree(target_dir)
                return True
            except Exception as e:
                logger.error("Failed to delete app directory %s: %s", target_dir, e)
                return False
        return False

    def list_templates(self) -> list[str]:
        if not TEMPLATES_DIR.exists():
            return []
        return [
            d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir() and (d / "meta.json").exists()
        ]

    def get_template_info(self, stack_type: str) -> dict[str, Any]:
        meta_path = TEMPLATES_DIR / stack_type / "meta.json"
        if meta_path.exists():
            try:
                return cast(dict[Any, Any], json.loads(meta_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        return {"name": stack_type, "description": stack_type}

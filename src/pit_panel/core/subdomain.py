"""Subdomain management."""

from pathlib import Path


class SubdomainManager:
    def __init__(self, apps_dir: str = "/opt/pit-panel/apps"):
        self.apps_dir = Path(apps_dir)

    def create_directory(self, subdomain: str) -> Path:
        path = self.apps_dir / subdomain
        path.mkdir(parents=True, exist_ok=True)
        return path

    def remove_directory(self, subdomain: str) -> bool:
        import shutil

        path = self.apps_dir / subdomain
        if path.exists():
            shutil.rmtree(path)
            return True
        return False

    def list_apps(self) -> list[str]:
        if not self.apps_dir.exists():
            return []
        return [d.name for d in self.apps_dir.iterdir() if d.is_dir()]

from pathlib import Path
from unittest.mock import patch

from pit_panel.core.app_manager import AppManager


def test_delete_app_exception(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    target_dir = apps_dir / "myapp"
    target_dir.mkdir(parents=True)

    manager = AppManager(apps_dir=str(apps_dir))

    with patch(
        "pit_panel.core.app_manager.shutil.rmtree", side_effect=OSError("Permission denied")
    ):
        result = manager.delete_app("myapp")

    assert result is False
    assert target_dir.exists()

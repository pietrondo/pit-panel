from pathlib import Path
from unittest.mock import patch

import pytest
import pit_panel.core.app_manager as app_manager_module
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


def test_get_template_info_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()
    (stack_dir / "meta.json").write_text('{"name": "custom_name", "description": "custom desc"}')

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)

    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    info = manager.get_template_info("mystack")
    assert info == {"name": "custom_name", "description": "custom desc"}


def test_get_template_info_not_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)

    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    info = manager.get_template_info("mystack")
    assert info == {"name": "mystack", "description": "mystack"}


def test_get_template_info_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()
    (stack_dir / "meta.json").write_text('invalid json {')

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)

    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    info = manager.get_template_info("mystack")
    assert info == {"name": "mystack", "description": "mystack"}

import pytest
from pathlib import Path
from pit_panel.core.app_manager import AppManager

def test_deploy_template_directory_traversal(tmp_path):
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    with pytest.raises(ValueError, match="Invalid stack type"):
        manager.deploy_template("test", "../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid stack type"):
        manager.deploy_template("test", "/etc/passwd")

    with pytest.raises(ValueError, match="Invalid stack type"):
        manager.deploy_template("test", "some/path")

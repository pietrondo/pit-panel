from pathlib import Path

import pytest

import pit_panel.core.app_manager as app_manager_module
from pit_panel.core.app_manager import AppManager


def test_deploy_template_directory_traversal(tmp_path: Path) -> None:
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    with pytest.raises(ValueError, match="Invalid stack type"):
        manager.deploy_template("test", "../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid stack type"):
        manager.deploy_template("test", "/etc/passwd")

    with pytest.raises(ValueError, match="Invalid stack type"):
        manager.deploy_template("test", "some/path")


def test_deploy_template_unknown_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)

    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    with pytest.raises(ValueError, match="Unknown stack type: dummy"):
        manager.deploy_template("test_sub", "dummy")


def test_deploy_template_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("domain: $subdomain\nimage: $image")
    (stack_dir / "static.txt").write_text("static content")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)

    apps_dir = tmp_path / "apps"
    manager = AppManager(apps_dir=str(apps_dir))

    result = manager.deploy_template("myapp", "mystack", {"image": "nginx:latest"})

    assert result == apps_dir / "myapp"
    assert result.exists()
    assert not (result / "meta.json").exists()
    assert (result / "docker-compose.yml").exists()
    assert (result / "docker-compose.yml").read_text() == "domain: myapp\nimage: nginx:latest"
    assert (result / "static.txt").exists()
    assert (result / "static.txt").read_text() == "static content"

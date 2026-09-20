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


def test_deploy_template_invalid_subdomain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "validstack"
    stack_dir.mkdir()
    (stack_dir / "meta.json").write_text('{"name": "validstack"}')

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    for bad in ("../../etc", "../foo", "a/b", "-bad", "x" * 100, ""):
        with pytest.raises(ValueError, match="Invalid subdomain"):
            manager.deploy_template(bad, "validstack")


def test_delete_app_invalid_subdomain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    for bad in ("../etc", "a/b", ""):
        with pytest.raises(ValueError, match="Invalid subdomain"):
            manager.delete_app(bad)


def test_deploy_template_unknown_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)

    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    with pytest.raises(ValueError, match="Invalid stack type"):
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

def test_deploy_template_wordpress_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "wordpress"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "wordpress"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("port: $PORT\ntitle: $WP_TITLE\nadmin: $WP_ADMIN_USER\nlocale: $WP_LOCALE\nsubdomain: $subdomain\nadmin_email: $WP_ADMIN_EMAIL")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)

    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    result = manager.deploy_template("mywp", "wordpress", {"WP_TITLE": "Custom Title"})

    assert result.exists()
    content = (result / "docker-compose.yml").read_text()
    assert "port: 8081" in content
    assert "title: Custom Title" in content
    assert "admin: admin" in content
    assert "locale: it_IT" in content
    assert "subdomain: mywp" in content
    assert "admin_email: admin@localhost" in content

def test_apply_mem_limits_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack", "mem_limit": "512m"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("services:\n  web:\n    image: nginx")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")

    compose_content = (result / "docker-compose.yml").read_text()
    assert "mem_limit: 512m" in compose_content

def test_apply_mem_limits_no_compose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack", "mem_limit": "512m"}')

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")
    assert not (result / "docker-compose.yml").exists()

def test_apply_mem_limits_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{invalid_json}')
    (stack_dir / "docker-compose.yml.tpl").write_text("services:\n  web:\n    image: nginx")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")
    compose_content = (result / "docker-compose.yml").read_text()
    assert "mem_limit" not in compose_content

def test_apply_mem_limits_no_mem_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("services:\n  web:\n    image: nginx")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")
    compose_content = (result / "docker-compose.yml").read_text()
    assert "mem_limit" not in compose_content

def test_apply_mem_limits_invalid_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack", "mem_limit": "512m"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("invalid_yaml:\n  - [\n")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")

def test_apply_mem_limits_not_dict_compose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack", "mem_limit": "512m"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("- item1\n- item2")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")
    compose_content = (result / "docker-compose.yml").read_text()
    assert "mem_limit" not in compose_content

def test_apply_mem_limits_not_dict_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack", "mem_limit": "512m"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("services:\n  - list_item")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")
    compose_content = (result / "docker-compose.yml").read_text()
    assert "mem_limit" not in compose_content

def test_delete_app_not_exists(tmp_path: Path) -> None:
    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    assert manager.delete_app("notexist") is False

def test_delete_app_not_dir(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    not_dir = apps_dir / "notdir"
    not_dir.write_text("file")

    manager = AppManager(apps_dir=str(apps_dir))
    assert manager.delete_app("notdir") is False

def test_list_templates_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack1 = templates_dir / "stack1"
    stack1.mkdir()
    (stack1 / "meta.json").write_text('{}')

    stack2 = templates_dir / "stack2"
    stack2.mkdir()

    file_in_dir = templates_dir / "somefile.txt"
    file_in_dir.write_text("file")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    templates = manager.list_templates()
    assert templates == ["stack1"]

def test_list_templates_no_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    assert manager.list_templates() == []

def test_delete_app_success(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    target_dir = apps_dir / "myapp"
    target_dir.mkdir(parents=True)

    manager = AppManager(apps_dir=str(apps_dir))

    assert manager.delete_app("myapp") is True
    assert not target_dir.exists()

def test_apply_mem_limits_service_not_dict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    (stack_dir / "meta.json").write_text('{"name": "mystack", "mem_limit": "512m"}')
    (stack_dir / "docker-compose.yml.tpl").write_text("services:\n  web: not_a_dict")

    monkeypatch.setattr(app_manager_module, "TEMPLATES_DIR", templates_dir)
    manager = AppManager(apps_dir=str(tmp_path / "apps"))

    result = manager.deploy_template("myapp", "mystack")
    compose_content = (result / "docker-compose.yml").read_text()
    assert "mem_limit" not in compose_content

def test_apply_mem_limits_meta_not_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    stack_dir = templates_dir / "mystack"
    stack_dir.mkdir()

    manager = AppManager(apps_dir=str(tmp_path / "apps"))
    target_dir = tmp_path / "apps" / "myapp"
    target_dir.mkdir(parents=True)

    manager._apply_mem_limits(target_dir, stack_dir)

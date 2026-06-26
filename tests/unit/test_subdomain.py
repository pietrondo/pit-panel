import pytest

from pit_panel.core.subdomain import SubdomainManager


@pytest.fixture
def temp_apps_dir(tmp_path):
    return tmp_path / "apps"


def test_subdomain_manager_init(temp_apps_dir):
    manager = SubdomainManager(str(temp_apps_dir))
    assert manager.apps_dir == temp_apps_dir


def test_create_directory(temp_apps_dir):
    manager = SubdomainManager(str(temp_apps_dir))

    path = manager.create_directory("testapp")

    assert path.exists()
    assert path.is_dir()
    assert path == temp_apps_dir / "testapp"

    # Check it doesn't fail if exists
    path2 = manager.create_directory("testapp")
    assert path2 == path


def test_remove_directory_exists(temp_apps_dir):
    manager = SubdomainManager(str(temp_apps_dir))
    manager.create_directory("testapp")

    # Create a file inside to ensure it removes non-empty dirs
    test_file = temp_apps_dir / "testapp" / "test.txt"
    test_file.touch()

    assert (temp_apps_dir / "testapp").exists()

    result = manager.remove_directory("testapp")

    assert result is True
    assert not (temp_apps_dir / "testapp").exists()


def test_remove_directory_not_exists(temp_apps_dir):
    manager = SubdomainManager(str(temp_apps_dir))

    result = manager.remove_directory("nonexistent")

    assert result is False


def test_list_apps_dir_not_exists(temp_apps_dir):
    manager = SubdomainManager(str(temp_apps_dir))

    assert manager.list_apps() == []


def test_list_apps(temp_apps_dir):
    manager = SubdomainManager(str(temp_apps_dir))

    manager.create_directory("app1")
    manager.create_directory("app2")

    # Create a file to ensure it's not listed
    temp_apps_dir.mkdir(parents=True, exist_ok=True)
    test_file = temp_apps_dir / "test.txt"
    test_file.touch()

    apps = manager.list_apps()

    assert len(apps) == 2
    assert "app1" in apps
    assert "app2" in apps
    assert "test.txt" not in apps

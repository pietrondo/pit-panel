"""Restore must only accept a plain backup name of this app's own archive."""

import tarfile
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import User
from pit_panel.web.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)
    monkeypatch.setattr("pit_panel.db.session._engine", None)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", None)
    return TestClient(create_app(s))


def _setup_session(client, monkeypatch):
    from pit_panel.db.session import get_db

    async def mock_get_user(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    for module in ("ops", "ops_files", "ops_terminal"):
        monkeypatch.setattr(f"pit_panel.web.routes.app_routes.{module}.get_user", mock_get_user)

    class MockSD:
        id = 1
        subdomain = "blog"
        base_domain = "example.com"
        is_main_domain = False
        app_type = "wordpress"
        host_port = 8081

    class MockResult:
        def scalar_one_or_none(self):
            return MockSD()

    class MockSession:
        async def execute(self, *args, **kwargs):
            return MockResult()

        async def commit(self):
            pass

        def add(self, obj):
            pass

    async def override_get_db():
        yield MockSession()

    client.app.dependency_overrides[get_db] = override_get_db


def _settings(tmp_path):
    return Settings(
        secret_key="test",
        apps_dir=str(tmp_path / "apps"),
        data_dir=str(tmp_path / "data"),
    )


def test_restore_rejects_path_in_name(client, monkeypatch, tmp_path):
    _setup_session(client, monkeypatch)
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.ops_files.get_settings", lambda: _settings(tmp_path)
    )
    try:
        resp = client.post("/apps/1/backup/restore", data={"name": "../other/x"})
        assert resp.status_code == 400
        assert "Invalid backup name" in resp.text
    finally:
        client.app.dependency_overrides.clear()


def test_restore_rejects_another_apps_archive(client, monkeypatch, tmp_path):
    _setup_session(client, monkeypatch)
    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.ops_files.get_settings", lambda: _settings(tmp_path)
    )
    monkeypatch.setattr(
        "pit_panel.core.docker_ops.DockerManager.run_compose_command", AsyncMock()
    )

    back_dir = tmp_path / "data" / "backups" / "blog"
    back_dir.mkdir(parents=True)
    other = tmp_path / "other-app"
    other.mkdir()
    (other / "index.php").write_text("<?php", encoding="utf-8")
    with tarfile.open(back_dir / "foreign.tar.gz", "w:gz") as tf:
        tf.add(other, arcname="other-app")

    try:
        resp = client.post("/apps/1/backup/restore", data={"name": "foreign"})
        assert resp.status_code == 400
        assert "does not belong" in resp.text
    finally:
        client.app.dependency_overrides.clear()

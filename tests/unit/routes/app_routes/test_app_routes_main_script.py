from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.db.models import Subdomain
from pit_panel.web.routes.app_routes.main import (
    _auto_setup_wordpress,
    _get_db_password,
    _has_db_container,
    _patch_vite_allowed_hosts,
    _render_apps_error,
    _resolve_subdomain,
)


def test_patch_vite_allowed_hosts(tmp_path):
    _patch_vite_allowed_hosts(tmp_path)
    assert not (tmp_path / "vite.config.pit.mjs").exists()

    (tmp_path / "vite.config.ts").write_text("export default {}")
    _patch_vite_allowed_hosts(tmp_path)
    assert (tmp_path / "vite.config.pit.mjs").exists()
    content = (tmp_path / "vite.config.pit.mjs").read_text()
    assert "mergeConfig" in content
    assert "vite.config.ts" in content


def test_get_db_password(tmp_path):
    class MockSettings:
        apps_dir = str(tmp_path)

    settings = MockSettings()
    subdomain = "testsub"
    (tmp_path / subdomain).mkdir()

    assert _get_db_password(settings, subdomain) is None

    (tmp_path / subdomain / ".env").write_text("DB_PASSWORD=secret\n")
    assert _get_db_password(settings, subdomain) == "secret"

    (tmp_path / subdomain / ".env").write_text("WORDPRESS_DB_PASSWORD='my_pass'\n")
    assert _get_db_password(settings, subdomain) == "my_pass"


def test_has_db_container(tmp_path):
    class MockSettings:
        apps_dir = str(tmp_path)

    settings = MockSettings()
    subdomain = "testsub"
    (tmp_path / subdomain).mkdir()

    assert not _has_db_container(settings, subdomain)

    (tmp_path / subdomain / "docker-compose.yml").write_text("image: mysql:8\n")
    assert _has_db_container(settings, subdomain)

    (tmp_path / subdomain / "docker-compose.yml").write_text("image: mariadb\n")
    assert _has_db_container(settings, subdomain)

    (tmp_path / subdomain / "docker-compose.yml").write_text("image: postgres:15\n")
    assert _has_db_container(settings, subdomain)

    (tmp_path / subdomain / "docker-compose.yml").write_text("image: nginx\n")
    assert not _has_db_container(settings, subdomain)


@pytest.mark.asyncio
async def test_app_analyze_repo_exceptions(monkeypatch):
    from fastapi import Request

    from pit_panel.web.routes.app_routes.main import app_analyze_repo

    async def mock_get_user_none(req, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_user", mock_get_user_none)

    req = MagicMock(spec=Request)
    req.headers = {}
    db = AsyncMock(spec=AsyncSession)

    resp = await app_analyze_repo(req, db)
    assert resp.body == b""

    async def mock_get_user_found(req, db):
        return MagicMock()

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_user", mock_get_user_found)

    async def mock_form():
        return {"repo_url": "test-url"}

    req.form = mock_form

    async def mock_analyze_repo_ve(url):
        raise ValueError("Invalid URL")

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.analyze_repo", mock_analyze_repo_ve)

    resp = await app_analyze_repo(req, db)
    assert b"Invalid URL" in resp.body

    async def mock_analyze_repo_ex(url):
        raise Exception("Some error")

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.analyze_repo", mock_analyze_repo_ex)

    resp = await app_analyze_repo(req, db)
    assert b"Errore: Some error" in resp.body


class MockResult:
    def __init__(self, val):
        self.val = val

    def scalar_one_or_none(self):
        return self.val

    def scalars(self):
        class MockScalars:
            def __init__(self, v):
                self.v = v

            def all(self):
                return self.v

        return MockScalars(self.val)


class MockSession:
    def __init__(self):
        self.val = None
        self.added = []

    def set_val(self, val):
        self.val = val

    async def execute(self, *args, **kwargs):
        return MockResult(self.val)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


@pytest.mark.asyncio
async def test_resolve_subdomain(monkeypatch):
    class MockSettings:
        base_domain = "test.com"

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_settings", lambda: MockSettings())

    db = MockSession()

    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.main.get_settings", lambda: MagicMock(base_domain=None)
    )
    sd, error = await _resolve_subdomain(db, 1, None, True, 0, "")
    assert error == "Base domain not configured. Set it in Settings."

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_settings", lambda: MockSettings())
    mock_sd = Subdomain(subdomain="_main_", app_type="test")
    db.set_val(mock_sd)
    sd, error = await _resolve_subdomain(db, 1, None, True, 0, "")
    assert error == "Main domain app already deployed"

    db.set_val(None)
    sd, error = await _resolve_subdomain(db, 1, None, True, 0, "")
    assert sd is not None
    assert sd.subdomain == "_main_"
    assert sd.is_main_domain is True

    db.set_val(None)
    sd, error = await _resolve_subdomain(db, 1, None, False, 1, "")
    assert error == "Subdomain not found"

    sd, error = await _resolve_subdomain(db, 1, None, False, 0, "invalid.name")
    assert "Invalid subdomain name" in error

    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.main.get_settings", lambda: MagicMock(base_domain=None)
    )
    sd, error = await _resolve_subdomain(db, 1, None, False, 0, "valid-name")
    assert error == "Base domain not configured. Set it in Settings."

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_settings", lambda: MockSettings())
    mock_sd_2 = Subdomain(subdomain="valid-name")
    db.set_val(mock_sd_2)
    sd, error = await _resolve_subdomain(db, 1, None, False, 0, "valid-name")
    assert sd == mock_sd_2

    db.set_val(None)
    sd, error = await _resolve_subdomain(db, 1, None, False, 0, "valid-name")
    assert sd is not None
    assert sd.subdomain == "valid-name"

    sd, error = await _resolve_subdomain(db, 1, None, False, 0, "")
    assert error == "Select an existing subdomain or enter a new name"


@pytest.mark.asyncio
async def test_render_apps_error(monkeypatch):
    from fastapi import Request

    db = MockSession()
    db.set_val([])

    req = MagicMock(spec=Request)
    req.headers = {"hx-request": "true"}
    resp = await _render_apps_error(None, None, db, "Some error", req)
    assert b"Some error" in resp.body

    class MockAppManager:
        def __init__(self, *args, **kwargs):
            pass

        def list_templates(self):
            return ["t1"]

        def get_template_info(self, t):
            return {}

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.AppManager", MockAppManager)

    def mock_render(template, **kwargs):
        return template

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.render", mock_render)

    resp = await _render_apps_error(None, None, db, "Some error", MagicMock(headers={}))
    assert resp == "apps.html"


@pytest.mark.asyncio
async def test_app_analyze_repo_success(monkeypatch):
    from fastapi import Request

    from pit_panel.web.routes.app_routes.main import app_analyze_repo

    async def mock_get_user_found(req, db):
        return MagicMock()

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.get_user", mock_get_user_found)

    async def mock_form():
        return {"repo_url": "test-repo"}

    req = MagicMock(spec=Request)
    req.form = mock_form

    class MockAnalysisResult:
        stack_type = "test-stack"
        display_name = "Test Stack"
        confidence = 95
        indicators = ["ind1"]

    async def mock_analyze_repo_ok(url):
        return MockAnalysisResult()

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.analyze_repo", mock_analyze_repo_ok)

    class MockAppManager:
        def __init__(self, *args, **kwargs):
            pass

        def list_templates(self):
            return ["test-stack"]

        def get_template_info(self, t):
            return {"display_name": "Meta Display", "icon": "X", "default_port": 1234}

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.AppManager", MockAppManager)

    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.main.get_settings", lambda: MagicMock(apps_dir="")
    )

    db = MockSession()
    db.set_val([Subdomain(id=1, subdomain="sub1", base_domain="b.com")])

    resp = await app_analyze_repo(req, db)
    assert b"sub1.b.com" in resp.body
    assert b"Test Stack" in resp.body or b"Meta Display" in resp.body

    # Test lower confidence
    class MockAnalysisResultLow:
        stack_type = "test-stack"
        display_name = "Test Stack"
        confidence = 50
        indicators = ["ind1"]

    async def mock_analyze_repo_low(url):
        return MockAnalysisResultLow()

    monkeypatch.setattr("pit_panel.web.routes.app_routes.main.analyze_repo", mock_analyze_repo_low)
    resp = await app_analyze_repo(req, db)
    assert b"badge-yellow" in resp.body

    # Test very lower confidence
    class MockAnalysisResultVeryLow:
        stack_type = "test-stack"
        display_name = "Test Stack"
        confidence = 40
        indicators = ["ind1"]

    async def mock_analyze_repo_verylow(url):
        return MockAnalysisResultVeryLow()

    monkeypatch.setattr(
        "pit_panel.web.routes.app_routes.main.analyze_repo", mock_analyze_repo_verylow
    )
    resp = await app_analyze_repo(req, db)
    assert b"badge-red" in resp.body


@pytest.mark.asyncio
async def test_auto_setup_wordpress(monkeypatch, tmp_path):
    class MockSettings:
        apps_dir = str(tmp_path)
        base_domain = "test.com"

    settings = MockSettings()
    sd = MagicMock()
    sd.subdomain = "testsub"

    (tmp_path / "testsub").mkdir()
    (tmp_path / "testsub" / ".env").write_text("WP_TITLE=My Test\nWP_ADMIN_USER=tester\n")

    class MockDockerMgr:
        async def exec_command(self, subdomain, container, cmd):
            self.called = True
            self.cmd = cmd

    dm = MockDockerMgr()

    import asyncio

    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await _auto_setup_wordpress(settings, sd, dm)

    assert dm.called
    assert "testsub" in dm.cmd[2] or "test.com" in dm.cmd[2]

    class MockDockerMgrEx:
        async def exec_command(self, subdomain, container, cmd):
            raise Exception("Fail")

    dm_ex = MockDockerMgrEx()
    await _auto_setup_wordpress(settings, sd, dm_ex)

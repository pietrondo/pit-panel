from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from pit_panel.db.models import User
from pit_panel.web.routes.security import (
    _abuseipdb_blacklist,
    _abuseipdb_check,
    security_ban_ip,
    security_malware_scan,
    security_malware_scan_full,
    security_malware_set_interval,
    security_malware_update_defs,
    security_overview,
    security_revoke_session,
    security_unban,
)


@pytest.mark.asyncio
async def test_abuseipdb_check_success(monkeypatch):
    import http.client

    class MockResponse:
        status = 200

        def read(self):
            return b'{"data": {"abuseConfidenceScore": 50, "totalReports": 10}}'

    class MockConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return MockResponse()

    monkeypatch.setattr(http.client, "HTTPSConnection", MockConnection)

    res = await _abuseipdb_check("1.2.3.4", "key")
    assert res == {"ip": "1.2.3.4", "score": 50, "reports": 10}


@pytest.mark.asyncio
async def test_abuseipdb_check_http_error(monkeypatch):
    import http.client

    class MockResponse:
        status = 404

    class MockConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return MockResponse()

    monkeypatch.setattr(http.client, "HTTPSConnection", MockConnection)

    res = await _abuseipdb_check("1.2.3.4", "key")
    assert res == {"ip": "1.2.3.4", "error": "HTTP 404"}


@pytest.mark.asyncio
async def test_abuseipdb_check_exception(monkeypatch):
    import http.client

    class MockConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise Exception("Conn Error")

    monkeypatch.setattr(http.client, "HTTPSConnection", MockConnection)

    res = await _abuseipdb_check("1.2.3.4", "key")
    assert res == {"ip": "1.2.3.4", "error": "Conn Error"}


@pytest.mark.asyncio
async def test_abuseipdb_blacklist_success(monkeypatch):
    import http.client

    class MockResponse:
        status = 200

        def read(self):
            return b'{"data": [{"ipAddress": "1.2.3.4", "abuseConfidenceScore": 100, "totalReports": 5, "lastReportedAt": "now"}]}'

    class MockConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return MockResponse()

    monkeypatch.setattr(http.client, "HTTPSConnection", MockConnection)

    res = await _abuseipdb_blacklist("key")
    assert len(res) == 1
    assert res[0] == {"ip": "1.2.3.4", "score": 100, "reports": 5, "last": "now"}


@pytest.mark.asyncio
async def test_abuseipdb_blacklist_http_error(monkeypatch):
    import http.client

    class MockResponse:
        status = 401

    class MockConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return MockResponse()

    monkeypatch.setattr(http.client, "HTTPSConnection", MockConnection)

    res = await _abuseipdb_blacklist("key")
    assert res == []


@pytest.mark.asyncio
async def test_abuseipdb_blacklist_exception(monkeypatch):
    import http.client

    class MockConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise Exception("Conn error")

    monkeypatch.setattr(http.client, "HTTPSConnection", MockConnection)

    res = await _abuseipdb_blacklist("key")
    assert res == []


@pytest.mark.asyncio
async def test_security_overview_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_overview(mock_request, mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_security_overview_authenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.render", mock_render)

    monkeypatch.setattr("pit_panel.web.routes.security.get_banned_ips", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "pit_panel.web.routes.security._firewall_status", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security._fail2ban_status", AsyncMock(return_value={})
    )

    mock_settings = MagicMock()
    mock_settings.abuseipdb_api_key = "key"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_result_attempts = MagicMock()
    mock_result_attempts.scalars.return_value.all.return_value = []

    mock_result_sessions = MagicMock()
    mock_result_sessions.__iter__.return_value = []

    mock_result_scan = MagicMock()
    mock_result_scan.scalars.return_value.all.return_value = []

    mock_result_settings = MagicMock()
    mock_result_settings.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [
        mock_result_attempts,
        mock_result_sessions,
        mock_result_scan,
        mock_result_settings,
    ]

    await security_overview(mock_request, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["user"] == user


@pytest.mark.asyncio
async def test_security_overview_scan_history_exception(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.render", mock_render)

    monkeypatch.setattr("pit_panel.web.routes.security.get_banned_ips", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "pit_panel.web.routes.security._firewall_status", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security._fail2ban_status", AsyncMock(return_value={})
    )

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    # Return valid iterables for the first two calls, raise exception on third (scan_history)
    mock_db.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        [],
        Exception("DB Error"),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    mock_engine = MagicMock()

    class AsyncContextManager:
        async def __aenter__(self):
            return AsyncMock(run_sync=AsyncMock())

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_engine.begin.return_value = AsyncContextManager()
    monkeypatch.setattr("pit_panel.db.session.get_engine", lambda: mock_engine)

    await security_overview(mock_request, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["scan_history"] == []


@pytest.mark.asyncio
async def test_security_unban_unauthenticated(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_unban(mock_request, ip="1.2.3.4", db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_security_unban_success(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_unban = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security.unban_ip_address", mock_unban)

    mock_render = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security._render_security_page", mock_render)

    await security_unban(mock_request, ip="1.2.3.4", db=mock_db)

    mock_unban.assert_called_once_with(mock_db, "1.2.3.4", 1)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["unban_result"] == {"ip": "1.2.3.4", "success": True}


@pytest.mark.asyncio
async def test_security_unban_no_ip(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_render = AsyncMock(return_value=HTMLResponse("rendered"))
    monkeypatch.setattr("pit_panel.web.routes.security._render_security_page", mock_render)

    await security_unban(mock_request, ip="", db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["unban_result"] is None


@pytest.mark.asyncio
async def test_security_revoke_session_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_revoke_session(mock_request, db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_security_revoke_session_success(monkeypatch):

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"session_id": "123"})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_revoke = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security.revoke_session", mock_revoke)

    res = await security_revoke_session(mock_request, db=mock_db)

    mock_revoke.assert_called_once_with(mock_db, 123)
    assert isinstance(res, RedirectResponse)


@pytest.mark.asyncio
async def test_security_revoke_session_no_id(monkeypatch):

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"session_id": "0"})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_revoke = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security.revoke_session", mock_revoke)

    res = await security_revoke_session(mock_request, db=mock_db)

    mock_revoke.assert_not_called()
    assert isinstance(res, RedirectResponse)


@pytest.mark.asyncio
async def test_security_ban_ip_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_ban_ip(mock_request, db=mock_db)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_security_ban_ip_success(monkeypatch):

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(
        return_value={"ip": "1.2.3.4", "reason": "test", "duration": "120"}
    )
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_ban = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security.ban_ip_address", mock_ban)

    mock_render = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security._render_security_page", mock_render)

    await security_ban_ip(mock_request, db=mock_db)

    mock_ban.assert_called_once_with(mock_db, "1.2.3.4", "test", 120)
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["ban_result"] == {"ip": "1.2.3.4", "ok": True}


@pytest.mark.asyncio
async def test_security_ban_no_ip(monkeypatch):

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"ip": ""})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_render = AsyncMock(return_value=HTMLResponse("rendered"))
    monkeypatch.setattr("pit_panel.web.routes.security._render_security_page", mock_render)

    await security_ban_ip(mock_request, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["ban_result"] is None


@pytest.mark.asyncio
async def test_security_malware_scan_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_malware_scan(mock_request, db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.body == b"Unauthorized"


@pytest.mark.asyncio
async def test_security_malware_scan_full_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_malware_scan_full(mock_request, db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.body == b"Unauthorized"


@pytest.mark.asyncio
async def test_security_malware_set_interval_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_malware_set_interval(mock_request, db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.body == b"Unauthorized"


@pytest.mark.asyncio
async def test_security_malware_update_defs_unauthenticated(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    async def mock_get_admin(request, db):
        return None

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    response = await security_malware_update_defs(mock_request, db=mock_db)
    assert isinstance(response, HTMLResponse)
    assert response.body == b"Unauthorized"


@pytest.mark.asyncio
async def test_security_malware_update_defs_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.update_definitions = AsyncMock(
        return_value={"ok": True, "output": "success"}
    )
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    res = await security_malware_update_defs(mock_request, db=mock_db)
    assert isinstance(res, HTMLResponse)
    assert b"Definitions updated:" in res.body


@pytest.mark.asyncio
async def test_security_malware_update_defs_fail(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.update_definitions = AsyncMock(
        return_value={"ok": False, "error": "failed"}
    )
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    res = await security_malware_update_defs(mock_request, db=mock_db)
    assert isinstance(res, HTMLResponse)
    assert b"Update failed: failed" in res.body


@pytest.mark.asyncio
async def test_security_malware_set_interval_new(monkeypatch):

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"hours": "24"})
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    res = await security_malware_set_interval(mock_request, db=mock_db)

    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    assert isinstance(res, HTMLResponse)
    assert b"Scan interval set to 24h" in res.body


@pytest.mark.asyncio
async def test_security_malware_set_interval_existing(monkeypatch):

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"hours": "1000"})  # tests max limit 168
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_row = MagicMock()
    mock_row.value = {}

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_row
    mock_db.execute.return_value = mock_result

    res = await security_malware_set_interval(mock_request, db=mock_db)

    assert mock_row.value == {"hours": 168}
    mock_db.commit.assert_called_once()
    assert isinstance(res, HTMLResponse)
    assert b"Scan interval set to 168h" in res.body


@pytest.mark.asyncio
async def test_security_malware_scan_full_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.scan_path = AsyncMock(
        return_value={"infected_total": 0, "scanned_total": 10}
    )
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    async def mock_overview(req, db):
        return HTMLResponse("overview")

    monkeypatch.setattr("pit_panel.web.routes.security.security_overview", mock_overview)

    res = await security_malware_scan_full(mock_request, db=mock_db)

    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2
    assert res.body == b"overview"
    added = mock_db.add.call_args[0][0]
    assert added.status == "completed"


@pytest.mark.asyncio
async def test_security_malware_scan_full_exception(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    mock_settings.apps_dir = "/apps"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.scan_path = AsyncMock(side_effect=Exception("Scan failed"))
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    async def mock_overview(req, db):
        return HTMLResponse("overview")

    monkeypatch.setattr("pit_panel.web.routes.security.security_overview", mock_overview)

    res = await security_malware_scan_full(mock_request, db=mock_db)

    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2
    assert res.body == b"overview"
    added = mock_db.add.call_args[0][0]
    assert added.status == "failed"


@pytest.mark.asyncio
async def test_security_malware_scan_missing_clamav_pull_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.check_docker_clamav = AsyncMock(return_value=False)
    mock_scanner.return_value.pull_clamav = AsyncMock(return_value="pulled successfully")
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    res = await security_malware_scan(mock_request, db=mock_db)

    assert isinstance(res, HTMLResponse)
    assert b"pulled successfully" in res.body


@pytest.mark.asyncio
async def test_security_malware_scan_missing_clamav_pull_fail(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.check_docker_clamav = AsyncMock(return_value=False)
    mock_scanner.return_value.pull_clamav = AsyncMock(side_effect=Exception("Failed to pull"))
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    res = await security_malware_scan(mock_request, db=mock_db)

    assert isinstance(res, HTMLResponse)
    assert b"Failed to pull ClamAV image" in res.body


@pytest.mark.asyncio
async def test_security_malware_scan_success(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.check_docker_clamav = AsyncMock(return_value=True)
    mock_scanner.return_value.scan_all = AsyncMock(
        return_value=[{"infected_total": 1, "scanned_total": 5}]
    )
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    mock_overview = AsyncMock(return_value=HTMLResponse("overview"))
    monkeypatch.setattr("pit_panel.web.routes.security.security_overview", mock_overview)

    await security_malware_scan(mock_request, db=mock_db)

    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2
    added = mock_db.add.call_args[0][0]
    assert added.status == "completed"
    assert added.infected_count == 1
    assert added.scanned_count == 5


@pytest.mark.asyncio
async def test_security_malware_scan_fail(monkeypatch):

    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_scanner = MagicMock()
    mock_scanner.return_value.check_docker_clamav = AsyncMock(return_value=True)
    mock_scanner.return_value.scan_all = AsyncMock(side_effect=Exception("Scan failed"))
    monkeypatch.setattr("pit_panel.web.routes.security.MalwareScanner", mock_scanner)

    mock_overview = AsyncMock(return_value=HTMLResponse("overview"))
    monkeypatch.setattr("pit_panel.web.routes.security.security_overview", mock_overview)

    await security_malware_scan(mock_request, db=mock_db)

    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2
    added = mock_db.add.call_args[0][0]
    assert added.status == "failed"


@pytest.mark.asyncio
async def test_security_overview_scan_history_exception_empty_row(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.render", mock_render)

    monkeypatch.setattr("pit_panel.web.routes.security.get_banned_ips", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "pit_panel.web.routes.security._firewall_status", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security._fail2ban_status", AsyncMock(return_value={})
    )

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    # Trigger exception when checking SystemSettings
    mock_db.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        [],
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        Exception("DB Error"),
    ]

    await security_overview(mock_request, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["scan_interval_hours"] == 6  # default based on pit_panel.security.malware_scanner


@pytest.mark.asyncio
async def test_security_overview_create_all_error(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.render", mock_render)

    monkeypatch.setattr("pit_panel.web.routes.security.get_banned_ips", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "pit_panel.web.routes.security._firewall_status", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security._fail2ban_status", AsyncMock(return_value={})
    )

    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    # Trigger exception on scan_history
    mock_db.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        [],
        Exception("DB Error"),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]

    mock_engine = MagicMock()

    class AsyncContextManager:
        async def __aenter__(self):
            return AsyncMock(run_sync=AsyncMock(side_effect=Exception("Create all failed")))

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_engine.begin.return_value = AsyncContextManager()
    monkeypatch.setattr("pit_panel.db.session.get_engine", lambda: mock_engine)

    with pytest.raises(Exception):
        await security_overview(mock_request, db=mock_db)


@pytest.mark.asyncio
async def test_security_overview_active_sessions(monkeypatch):
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock(spec=AsyncSession)

    user = User(id=1, username="admin", is_admin=True)

    async def mock_get_admin(request, db):
        return user

    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_render = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.security.render", mock_render)

    monkeypatch.setattr("pit_panel.web.routes.security.get_banned_ips", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "pit_panel.web.routes.security._firewall_status", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security._fail2ban_status", AsyncMock(return_value={})
    )

    mock_settings = MagicMock()
    mock_settings.abuseipdb_api_key = "key"
    monkeypatch.setattr("pit_panel.web.routes.security.get_settings", lambda: mock_settings)

    mock_result_attempts = MagicMock()
    mock_result_attempts.scalars.return_value.all.return_value = []

    mock_session = MagicMock()
    mock_session.id = 1
    mock_session.ip = "1.2.3.4"
    mock_session.created_at = "now"

    mock_result_sessions = MagicMock()
    mock_result_sessions.__iter__.return_value = [(mock_session, "admin")]

    mock_result_scan = MagicMock()
    mock_result_scan.scalars.return_value.all.return_value = []

    mock_row = MagicMock()
    mock_row.value = {"hours": 12}

    mock_result_settings = MagicMock()
    mock_result_settings.scalar_one_or_none.return_value = mock_row

    mock_db.execute.side_effect = [
        mock_result_attempts,
        mock_result_sessions,
        mock_result_scan,
        mock_result_settings,
    ]

    await security_overview(mock_request, db=mock_db)

    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert len(kwargs["sessions"]) == 1
    assert kwargs["scan_interval_hours"] == 12

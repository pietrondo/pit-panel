import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pit_panel.web.routes.security_abuseipdb import router

@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_abuseipdb.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    return client

def test_abuseipdb_blacklist_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_abuseipdb.get_admin", AsyncMock(return_value=None))

    response = c.get("/security/abuseipdb-blacklist")
    assert response.status_code == 401

def test_abuseipdb_check_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_abuseipdb.get_admin", AsyncMock(return_value=None))

    response = c.post("/security/abuseipdb-check")
    assert response.status_code == 401

def test_abuseipdb_blacklist_no_key(client, monkeypatch):
    monkeypatch.setattr("pit_panel.web.routes.security_abuseipdb.get_settings", MagicMock(return_value=MagicMock(abuseipdb_api_key="")))
    response = client.get("/security/abuseipdb-blacklist")
    assert response.status_code == 200
    assert "No AbuseIPDB API key configured" in response.text

def test_abuseipdb_check_score_colors(client, monkeypatch):
    monkeypatch.setattr("pit_panel.web.routes.security_abuseipdb._abuseipdb_check", AsyncMock(return_value={"ip": "1.1.1.1", "score": 10, "reports": 0}))
    response = client.post("/security/abuseipdb-check", data={"ip": "1.1.1.1", "api_key": "test"})
    assert "text-green-500" in response.text

    monkeypatch.setattr("pit_panel.web.routes.security_abuseipdb._abuseipdb_check", AsyncMock(return_value={"ip": "2.2.2.2", "score": 50, "reports": 0}))
    response = client.post("/security/abuseipdb-check", data={"ip": "2.2.2.2", "api_key": "test"})
    assert "text-orange-500" in response.text

    monkeypatch.setattr("pit_panel.web.routes.security_abuseipdb._abuseipdb_check", AsyncMock(return_value={"ip": "3.3.3.3", "score": 90, "reports": 0}))
    response = client.post("/security/abuseipdb-check", data={"ip": "3.3.3.3", "api_key": "test"})
    assert "text-red-500" in response.text

def test_abuseipdb_check_http_client(monkeypatch):
    import http.client

    mock_conn = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"data": {"abuseConfidenceScore": 50, "totalReports": 5}}'
    mock_conn.getresponse.return_value = mock_resp

    with patch("http.client.HTTPSConnection", return_value=mock_conn):
        import asyncio
        from pit_panel.web.routes.security_abuseipdb import _abuseipdb_check
        result = asyncio.run(_abuseipdb_check("1.1.1.1", "key"))
        assert result["score"] == 50
        assert result["reports"] == 5

def test_abuseipdb_check_http_error(monkeypatch):
    import http.client

    mock_conn = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 401
    mock_conn.getresponse.return_value = mock_resp

    with patch("http.client.HTTPSConnection", return_value=mock_conn):
        import asyncio
        from pit_panel.web.routes.security_abuseipdb import _abuseipdb_check
        result = asyncio.run(_abuseipdb_check("1.1.1.1", "key"))
        assert "HTTP 401" in result["error"]

def test_abuseipdb_check_exception(monkeypatch):
    import http.client

    with patch("http.client.HTTPSConnection", side_effect=Exception("Timeout")):
        import asyncio
        from pit_panel.web.routes.security_abuseipdb import _abuseipdb_check
        result = asyncio.run(_abuseipdb_check("1.1.1.1", "key"))
        assert "Timeout" in result["error"]

def test_abuseipdb_blacklist_http_client(monkeypatch):
    import http.client

    mock_conn = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"data": [{"ipAddress": "1.1.1.1", "abuseConfidenceScore": 100, "totalReports": 10, "lastReportedAt": "2023"}]}'
    mock_conn.getresponse.return_value = mock_resp

    with patch("http.client.HTTPSConnection", return_value=mock_conn):
        import asyncio
        from pit_panel.web.routes.security_abuseipdb import _abuseipdb_blacklist
        result = asyncio.run(_abuseipdb_blacklist("key"))
        assert len(result) == 1
        assert result[0]["ip"] == "1.1.1.1"

def test_abuseipdb_blacklist_http_error(monkeypatch):
    import http.client

    mock_conn = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 401
    mock_conn.getresponse.return_value = mock_resp

    with patch("http.client.HTTPSConnection", return_value=mock_conn):
        import asyncio
        from pit_panel.web.routes.security_abuseipdb import _abuseipdb_blacklist
        result = asyncio.run(_abuseipdb_blacklist("key"))
        assert len(result) == 0

def test_abuseipdb_blacklist_exception(monkeypatch):
    import http.client

    with patch("http.client.HTTPSConnection", side_effect=Exception("Timeout")):
        import asyncio
        from pit_panel.web.routes.security_abuseipdb import _abuseipdb_blacklist
        result = asyncio.run(_abuseipdb_blacklist("key"))
        assert len(result) == 0

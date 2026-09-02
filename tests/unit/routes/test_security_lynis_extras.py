import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pit_panel.web.routes.security_lynis import router

@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_lynis.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    return client

def test_lynis_audit_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_lynis.get_admin", AsyncMock(return_value=None))

    response = c.post("/security/lynis/audit")
    assert response.status_code == 401

def test_lynis_report_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_lynis.get_admin", AsyncMock(return_value=None))

    response = c.get("/security/lynis/report")
    assert response.status_code == 401

def test_lynis_report_file_not_found(client, monkeypatch):
    import aiofiles
    import unittest.mock

    mock_aio_open = unittest.mock.MagicMock()
    mock_aio_open.return_value.__aenter__.side_effect = Exception("File not found")

    with unittest.mock.patch("aiofiles.open", mock_aio_open):
        response = client.get("/security/lynis/report")
        assert response.status_code == 200
        assert "error" in response.json()
        assert "File not found" in response.json()["error"]

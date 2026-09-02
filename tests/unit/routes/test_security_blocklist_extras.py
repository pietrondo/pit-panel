from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pit_panel.web.routes.security_blocklist import router


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_blocklist.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    return client


def test_blocklist_page_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr(
        "pit_panel.web.routes.security_blocklist.get_admin", AsyncMock(return_value=None)
    )

    response = c.get("/security/blocklist")
    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/login"


def test_blocklist_import_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr(
        "pit_panel.web.routes.security_blocklist.get_admin", AsyncMock(return_value=None)
    )

    response = c.post("/security/blocklist/import")
    assert response.status_code == 200
    assert "Unauthorized" in response.text


def test_blocklist_import_invalid_source(client):
    response = client.post("/security/blocklist/import", data={"source": "invalid_source"})
    assert response.status_code == 200
    assert "Invalid source" in response.text


def test_blocklist_import_no_ips(client, monkeypatch):
    monkeypatch.setattr(
        "pit_panel.web.routes.security_blocklist.fetch_blocklist", AsyncMock(return_value=[])
    )

    response = client.post("/security/blocklist/import", data={"source": "firehol_level1"})
    assert response.status_code == 200
    assert "No IPs found" in response.text


def test_blocklist_import_success(client, monkeypatch):
    monkeypatch.setattr(
        "pit_panel.web.routes.security_blocklist.fetch_blocklist",
        AsyncMock(return_value=["1.1.1.1", "2.2.2.2"]),
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_blocklist.ban_ips_bulk", AsyncMock(return_value=2)
    )

    response = client.post("/security/blocklist/import", data={"source": "firehol_level1"})
    assert response.status_code == 200
    assert "Imported 2/2 IPs from FireHOL Level 1" in response.text

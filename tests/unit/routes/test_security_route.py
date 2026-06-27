import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_security_blocklist_import(monkeypatch):
    from pit_panel.web.routes.security import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    mock_get_admin = AsyncMock()
    mock_get_admin.return_value = MagicMock(id=1)
    monkeypatch.setattr("pit_panel.web.routes.security.get_admin", mock_get_admin)

    mock_fetch_blocklist = AsyncMock()
    mock_fetch_blocklist.return_value = ["192.168.1.1"]
    monkeypatch.setattr("pit_panel.web.routes.security.fetch_blocklist", mock_fetch_blocklist)

    mock_ban_ips_bulk = AsyncMock()
    mock_ban_ips_bulk.return_value = 1
    monkeypatch.setattr("pit_panel.web.routes.security.ban_ips_bulk", mock_ban_ips_bulk)

    response = client.post("/security/blocklist/import", data={"source": "firehol_level1"})

    assert response.status_code == 200
    assert "Imported 1/1 IPs" in response.text

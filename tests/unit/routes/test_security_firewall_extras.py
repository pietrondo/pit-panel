import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pit_panel.web.routes.security_firewall import router

@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_firewall.get_admin",
        AsyncMock(return_value=MagicMock(id=1)),
    )
    return client

def test_enable_firewall_fail(client, monkeypatch):
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._enable_ufw", AsyncMock(return_value=False))

    response = client.post("/security/firewall/enable")
    assert response.status_code == 200
    assert "Failed to enable firewall" in response.text

def test_disable_firewall_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_firewall.get_admin", AsyncMock(return_value=None))

    response = c.post("/security/firewall/disable")
    assert response.status_code == 401

def test_disable_firewall_fail(client, monkeypatch):
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._disable_ufw", AsyncMock(return_value=False))

    response = client.post("/security/firewall/disable")
    assert response.status_code == 200
    assert "Failed to disable firewall" in response.text

def test_add_rule_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_firewall.get_admin", AsyncMock(return_value=None))

    response = c.post("/security/firewall/rule/add", data={"port": "80"})
    assert response.status_code == 401

def test_add_rule_invalid_action(client):
    response = client.post("/security/firewall/rule/add", data={"port": "80", "action": "invalid"})
    assert response.status_code == 400
    assert "Invalid action" in response.text

def test_add_rule_invalid_protocol(client):
    response = client.post("/security/firewall/rule/add", data={"port": "80", "protocol": "invalid"})
    assert response.status_code == 400
    assert "Invalid protocol" in response.text

def test_add_rule_invalid_port(client):
    response = client.post("/security/firewall/rule/add", data={"port": "80;rm -rf /"})
    assert response.status_code == 400
    assert "Invalid port" in response.text

def test_add_rule_invalid_source(client):
    response = client.post("/security/firewall/rule/add", data={"port": "80", "source": "invalid_ip"})
    assert response.status_code == 400
    assert "Invalid source IP or network" in response.text

def test_add_rule_fail(client, monkeypatch):
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._add_ufw_rule", AsyncMock(return_value=False))

    response = client.post("/security/firewall/rule/add", data={"port": "80"})
    assert response.status_code == 200
    assert "Failed to add rule" in response.text

def test_delete_rule_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_firewall.get_admin", AsyncMock(return_value=None))

    response = c.post("/security/firewall/rule/delete", data={"index": 1})
    assert response.status_code == 401

def test_delete_rule_fail(client, monkeypatch):
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._delete_ufw_rule", AsyncMock(return_value=False))

    response = client.post("/security/firewall/rule/delete", data={"index": 1})
    assert response.status_code == 200
    assert "Failed to delete rule" in response.text

def test_delete_rule_value_error(client, monkeypatch):
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.web.routes.security_firewall._delete_ufw_rule", AsyncMock(side_effect=ValueError("Cannot delete SSH rule")))

    response = client.post("/security/firewall/rule/delete", data={"index": 1})
    assert response.status_code == 400
    assert "Cannot delete SSH rule" in response.text

def test_enable_firewall_unauth(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    monkeypatch.setattr("pit_panel.web.routes.security_firewall.get_admin", AsyncMock(return_value=None))

    response = c.post("/security/firewall/enable")
    assert response.status_code == 401

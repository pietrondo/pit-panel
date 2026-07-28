from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pit_panel.web.routes.security_ddos import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app

@pytest.fixture
def client(app):
    return TestClient(app)

@pytest.mark.asyncio
async def test_security_ddos_status_unauthorized(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    response = client.get("/security/ddos/status")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_security_ddos_status_active(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_is_shield_active = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._is_shield_active", mock_is_shield_active
    )

    response = client.get("/security/ddos/status")
    assert response.status_code == 200
    assert "Protezione ATTIVA" in response.text

@pytest.mark.asyncio
async def test_security_ddos_status_inactive(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_is_shield_active = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._is_shield_active", mock_is_shield_active
    )

    response = client.get("/security/ddos/status")
    assert response.status_code == 200
    assert "Non attiva" in response.text

@pytest.mark.asyncio
async def test_security_ddos_enable_success(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_ensure_sudoers = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._ensure_sudoers", mock_ensure_sudoers)

    mock_enable_shield = AsyncMock(return_value=[])
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._enable_shield", mock_enable_shield)

    mock_run_cmd = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    response = client.post("/security/ddos/enable")
    assert response.status_code == 200
    assert "Anti-DDoS Shield attivato" in response.text

@pytest.mark.asyncio
async def test_security_ddos_enable_sudoers_fail(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_ensure_sudoers = AsyncMock(return_value=False)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._ensure_sudoers", mock_ensure_sudoers)

    response = client.post("/security/ddos/enable")
    assert response.status_code == 200
    assert "iptables non è nei sudoers" in response.text

@pytest.mark.asyncio
async def test_security_ddos_enable_with_errors(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_ensure_sudoers = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._ensure_sudoers", mock_ensure_sudoers)

    mock_enable_shield = AsyncMock(return_value=["Error 1"])
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._enable_shield", mock_enable_shield)

    mock_run_cmd = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    response = client.post("/security/ddos/enable")
    assert response.status_code == 200
    assert "Shield attivato con avvisi" in response.text
    assert "Error 1" in response.text

@pytest.mark.asyncio
async def test_security_ddos_disable(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_disable_shield = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._disable_shield", mock_disable_shield)

    response = client.post("/security/ddos/disable")
    assert response.status_code == 200
    assert "Shield rimosso" in response.text

@pytest.mark.asyncio
async def test_security_ddos_block_ip_success(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    response = client.post("/security/ddos/block-ip", data={"ip": "1.2.3.4"})
    assert response.status_code == 200
    assert "1.2.3.4 bloccato" in response.text

@pytest.mark.asyncio
async def test_security_ddos_block_ip_invalid(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    response = client.post("/security/ddos/block-ip", data={"ip": "invalid-ip"})
    assert response.status_code == 400
    assert "IP non valido" in response.text

@pytest.mark.asyncio
async def test_security_ddos_block_ip_fail(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_iptables = AsyncMock(return_value=False)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    response = client.post("/security/ddos/block-ip", data={"ip": "1.2.3.4"})
    assert response.status_code == 200
    assert "Impossibile bloccare 1.2.3.4" in response.text

@pytest.mark.asyncio
async def test_security_ddos_unblock_ip_success(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    response = client.post("/security/ddos/unblock-ip", data={"ip": "1.2.3.4"})
    assert response.status_code == 200
    assert "1.2.3.4 sbloccato" in response.text

@pytest.mark.asyncio
async def test_security_ddos_unblock_ip_invalid(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    response = client.post("/security/ddos/unblock-ip", data={"ip": "invalid-ip"})
    assert response.status_code == 400
    assert "IP non valido" in response.text

@pytest.mark.asyncio
async def test_security_ddos_unblock_ip_fail(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_iptables = AsyncMock(return_value=False)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    response = client.post("/security/ddos/unblock-ip", data={"ip": "1.2.3.4"})
    assert response.status_code == 200
    assert "Regola non trovata per 1.2.3.4" in response.text

@pytest.mark.asyncio
async def test_security_ddos_top_connections(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = """State Recv-Q Send-Q Local Address:Port Peer Address:Port
ESTAB 0      0      10.0.0.1:443       1.2.3.4:12345
ESTAB 0      0      10.0.0.1:443       1.2.3.4:12346
ESTAB 0      0      10.0.0.1:443       5.6.7.8:12347
"""
    mock_run_cmd = AsyncMock(return_value=mock_res)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    response = client.get("/security/ddos/top-connections")
    assert response.status_code == 200
    assert "1.2.3.4" in response.text
    assert "2 conn" in response.text
    assert "5.6.7.8" in response.text
    assert "1 conn" in response.text

@pytest.mark.asyncio
async def test_security_ddos_top_connections_fallback(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_res_fail = MagicMock(returncode=1)
    mock_res_ok = MagicMock(returncode=0)
    mock_res_ok.stdout = """State Recv-Q Send-Q Local Address:Port Peer Address:Port
ESTAB 0      0      10.0.0.1:443       1.2.3.4:12345
"""
    mock_run_cmd = AsyncMock(side_effect=[mock_res_fail, mock_res_ok])
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    response = client.get("/security/ddos/top-connections")
    assert response.status_code == 200
    assert "1.2.3.4" in response.text

@pytest.mark.asyncio
async def test_security_ddos_top_connections_empty(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = """State Recv-Q Send-Q Local Address:Port Peer Address:Port
"""
    mock_run_cmd = AsyncMock(return_value=mock_res)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    response = client.get("/security/ddos/top-connections")
    assert response.status_code == 200
    assert "Nessuna connessione attiva rilevata" in response.text

@pytest.mark.asyncio
async def test_security_protect_all(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    monkeypatch.setattr("pit_panel.core.security._get_client_ip", lambda r: "1.2.3.4")
    monkeypatch.setattr("pit_panel.core.security._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.core.security._enable_ufw", AsyncMock(return_value=True))

    mock_res_success = MagicMock(returncode=0)
    mock_run_cmd = AsyncMock(return_value=mock_res_success)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._enable_shield", AsyncMock(return_value=[])
    )

    response = client.post("/security/protect-all")
    assert response.status_code == 200
    assert "Firewall UFW attivato" in response.text
    assert "Fail2ban: sshd attivo" in response.text
    assert "Anti-DDoS Shield attivato" in response.text

@pytest.mark.asyncio
async def test_security_protect_all_fail(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    monkeypatch.setattr("pit_panel.core.security._get_client_ip", lambda r: "1.2.3.4")
    monkeypatch.setattr("pit_panel.core.security._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.core.security._enable_ufw", AsyncMock(return_value=False))

    mock_res_fail = MagicMock(returncode=1)
    mock_run_cmd = AsyncMock(return_value=mock_res_fail)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=False)
    )

    response = client.post("/security/protect-all")
    assert response.status_code == 200
    assert "Firewall: errore" in response.text
    assert "Fail2ban: sshd non disponibile" in response.text
    assert "Anti-DDoS: iptables non nei sudoers" in response.text

@pytest.mark.asyncio
async def test_internal_ensure_sudoers(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _ensure_sudoers

    mock_res = MagicMock(returncode=0)
    mock_run_cmd = AsyncMock(return_value=mock_res)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await _ensure_sudoers()
    assert res is True

@pytest.mark.asyncio
async def test_internal_ensure_sudoers_no_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _ensure_sudoers

    mock_res_fail = MagicMock(returncode=1)
    mock_run_cmd = AsyncMock(return_value=mock_res_fail)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    mock_settings = MagicMock()
    mock_settings.sudo_password = ""
    monkeypatch.setattr("pit_panel.config.get_settings", lambda: mock_settings)

    res = await _ensure_sudoers()
    assert res is False

@pytest.mark.asyncio
async def test_internal_ensure_sudoers_with_password(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from pit_panel.web.routes.security_ddos import _ensure_sudoers

    mock_res_fail = MagicMock(returncode=1)
    mock_res_success = MagicMock(returncode=0)
    mock_run_cmd = AsyncMock(side_effect=[mock_res_fail, mock_res_success])
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    mock_settings = MagicMock()
    mock_settings.sudo_password = "password"
    monkeypatch.setattr("pit_panel.config.get_settings", lambda: mock_settings)

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_create_exec = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_exec)

    res = await _ensure_sudoers()
    assert res is True

@pytest.mark.asyncio
async def test_internal_ensure_sudoers_with_password_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from pit_panel.web.routes.security_ddos import _ensure_sudoers

    mock_res_fail = MagicMock(returncode=1)
    mock_run_cmd = AsyncMock(return_value=mock_res_fail)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    mock_settings = MagicMock()
    mock_settings.sudo_password = "password"
    monkeypatch.setattr("pit_panel.config.get_settings", lambda: mock_settings)

    mock_create_exec = AsyncMock(side_effect=Exception("Failed"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_exec)

    res = await _ensure_sudoers()
    assert res is False

@pytest.mark.asyncio
async def test_internal_iptables(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _iptables
    mock_res = MagicMock(returncode=0)
    mock_run_cmd = AsyncMock(return_value=mock_res)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await _iptables(["-L"])
    assert res is True
    mock_run_cmd.assert_called_once_with(["sudo", "-n", "iptables", "-L"], timeout=10)

@pytest.mark.asyncio
async def test_internal_is_shield_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _is_shield_active
    mock_res = MagicMock(returncode=0, stderr="")
    mock_run_cmd = AsyncMock(return_value=mock_res)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await _is_shield_active()
    assert res is True

@pytest.mark.asyncio
async def test_internal_is_shield_active_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _is_shield_active
    mock_res = MagicMock(returncode=0, stderr="No such file")
    mock_run_cmd = AsyncMock(return_value=mock_res)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await _is_shield_active()
    assert res is False

@pytest.mark.asyncio
async def test_internal_enable_shield(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _enable_shield

    # Mock _iptables to return True for everything except "-N"
    # Actually we can just mock it to always return True
    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    errors = await _enable_shield()
    assert len(errors) == 0

@pytest.mark.asyncio
async def test_internal_enable_shield_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _enable_shield

    mock_iptables = AsyncMock(return_value=False)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    errors = await _enable_shield()
    assert len(errors) > 0
    assert any("⚠️" in e for e in errors)

@pytest.mark.asyncio
async def test_internal_disable_shield(monkeypatch: pytest.MonkeyPatch) -> None:
    from pit_panel.web.routes.security_ddos import _disable_shield

    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    await _disable_shield()
    assert mock_iptables.call_count == 3
@pytest.mark.asyncio
async def test_security_ddos_enable_exception(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)

    mock_ensure_sudoers = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._ensure_sudoers", mock_ensure_sudoers)

    mock_enable_shield = AsyncMock(return_value=[])
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._enable_shield", mock_enable_shield)

    mock_run_cmd = AsyncMock(side_effect=Exception("Wait for timeout failed"))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    response = client.post("/security/ddos/enable")
    assert response.status_code == 200
    assert "Anti-DDoS Shield attivato" in response.text

@pytest.mark.asyncio
async def test_security_ddos_disable_unauthorized(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    response = client.post("/security/ddos/disable")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_security_ddos_block_ip_unauthorized(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    response = client.post("/security/ddos/block-ip")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_security_ddos_unblock_ip_unauthorized(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_get_admin = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    response = client.post("/security/ddos/unblock-ip")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_security_ddos_top_connections_unauthorized(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_get_admin = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    response = client.get("/security/ddos/top-connections")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_security_protect_all_unauthorized(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    response = client.post("/security/protect-all")
    assert response.status_code == 401
@pytest.mark.asyncio
async def test_security_ddos_enable_unauthorized(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=None)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    response = client.post("/security/ddos/enable")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_security_protect_all_fail_shield(client, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get_admin = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.get_admin", mock_get_admin)
    monkeypatch.setattr("pit_panel.core.security._get_client_ip", lambda r: "1.2.3.4")
    monkeypatch.setattr("pit_panel.core.security._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.core.security._enable_ufw", AsyncMock(return_value=True))

    mock_res_success = MagicMock(returncode=0)
    mock_run_cmd = AsyncMock(return_value=mock_res_success)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._enable_shield",
        AsyncMock(return_value=["Warning"])
    )

    response = client.post("/security/protect-all")
    assert response.status_code == 200
    assert "Anti-DDoS Shield attivato (con avvisi)" in response.text

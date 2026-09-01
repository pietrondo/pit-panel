from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.web.routes.security_ddos import (
    _IPTABLES_RULES,
    DDOS_CHAIN,
    _disable_shield,
    _enable_shield,
    _ensure_sudoers,
    _iptables,
    _is_shield_active,
    security_ddos_block_ip,
    security_ddos_disable,
    security_ddos_enable,
    security_ddos_status,
    security_ddos_top_connections,
    security_ddos_unblock_ip,
    security_protect_all,
)


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ensure_sudoers_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    result = await _ensure_sudoers()
    assert result is True
    mock_run_cmd.assert_called_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ensure_sudoers_no_password(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 1
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    mock_get_settings = MagicMock()
    mock_settings = MagicMock()
    mock_settings.sudo_password = None
    mock_get_settings.return_value = mock_settings
    monkeypatch.setattr("pit_panel.config.get_settings", mock_get_settings)

    result = await _ensure_sudoers()
    assert result is False
    assert mock_run_cmd.call_count == 1


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ensure_sudoers_with_password(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run_cmd = AsyncMock()
    mock_run_cmd.side_effect = [MagicMock(returncode=1), MagicMock(returncode=0)]
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    mock_get_settings = MagicMock()
    mock_settings = MagicMock()
    mock_settings.sudo_password = "password123"
    mock_get_settings.return_value = mock_settings
    monkeypatch.setattr("pit_panel.config.get_settings", mock_get_settings)

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_create_subprocess_exec = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)

    result = await _ensure_sudoers()
    assert result is True
    assert mock_run_cmd.call_count == 2
    mock_create_subprocess_exec.assert_called_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_ensure_sudoers_with_password_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run_cmd = AsyncMock()
    mock_run_cmd.side_effect = [MagicMock(returncode=1), MagicMock(returncode=0)]
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    mock_get_settings = MagicMock()
    mock_settings = MagicMock()
    mock_settings.sudo_password = "password123"
    mock_get_settings.return_value = mock_settings
    monkeypatch.setattr("pit_panel.config.get_settings", mock_get_settings)

    mock_create_subprocess_exec = AsyncMock(side_effect=Exception("Test Error"))
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)

    result = await _ensure_sudoers()
    assert result is False
    assert mock_run_cmd.call_count == 1
    mock_create_subprocess_exec.assert_called_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_iptables(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    result = await _iptables(["-L"])
    assert result is True
    mock_run_cmd.assert_called_once_with(["sudo", "-n", "iptables", "-L"], timeout=10)


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_is_shield_active(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    mock_run_cmd.return_value.stderr = ""
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    result = await _is_shield_active()
    assert result is True
    mock_run_cmd.assert_called_once_with(
        ["sudo", "-n", "iptables", "-L", DDOS_CHAIN, "-n"], timeout=5
    )


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_is_shield_active_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    mock_run_cmd.return_value.stderr = "No such file"
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    result = await _is_shield_active()
    assert result is False


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_enable_shield(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    results = await _enable_shield()
    assert results == []
    # Assert called for all rules + 1 for INPUT + 2 for ports + 2 for -N (-F, -X)
    assert (
        mock_iptables.call_count
        == len(_IPTABLES_RULES) + 1 + 2 + sum(1 for r in _IPTABLES_RULES if r[0] == "-N") * 2
    )


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_enable_shield_with_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_iptables = AsyncMock(return_value=False)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    results = await _enable_shield()
    assert len(results) == sum(1 for r in _IPTABLES_RULES if r[0] != "-N")
    assert "⚠️ " in results[0]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_disable_shield(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    await _disable_shield()
    assert mock_iptables.call_count == 3


@pytest.fixture  # type: ignore[untyped-decorator]
def mock_request() -> Request:
    return MagicMock(spec=Request)


@pytest.fixture  # type: ignore[untyped-decorator]
def mock_db() -> AsyncSession:
    return MagicMock(spec=AsyncSession)


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_status_unauthorized(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=None)
    )
    res = await security_ddos_status(mock_request, mock_db)
    assert res.status_code == 401


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_status_active(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._is_shield_active", AsyncMock(return_value=True)
    )
    res = await security_ddos_status(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Protezione ATTIVA" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_status_inactive(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._is_shield_active", AsyncMock(return_value=False)
    )
    res = await security_ddos_status(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Non attiva" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_enable_unauthorized(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=None)
    )
    res = await security_ddos_enable(mock_request, mock_db)
    assert res.status_code == 401


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_enable_no_sudoers(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=False)
    )
    res = await security_ddos_enable(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "iptables non è nei sudoers" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_enable_success(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._enable_shield", AsyncMock(return_value=[])
    )
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await security_ddos_enable(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Anti-DDoS Shield attivato" in res.body.decode()
    mock_run_cmd.assert_called_once_with(
        ["sudo", "-n", "fail2ban-client", "start", "sshd-ddos"], timeout=10
    )


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_enable_with_errors(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._enable_shield", AsyncMock(return_value=["error1"])
    )
    mock_run_cmd = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await security_ddos_enable(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Shield attivato con avvisi" in res.body.decode()
    assert "error1" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_disable_unauthorized(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=None)
    )
    res = await security_ddos_disable(mock_request, mock_db)
    assert res.status_code == 401


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_disable_success(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_disable_shield = AsyncMock()
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._disable_shield", mock_disable_shield)

    res = await security_ddos_disable(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Shield rimosso" in res.body.decode()
    mock_disable_shield.assert_called_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_block_ip_unauthorized(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=None)
    )
    res = await security_ddos_block_ip(mock_request, mock_db)
    assert res.status_code == 401


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_block_ip_invalid(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_request.form = AsyncMock(return_value={"ip": "invalid_ip"})

    res = await security_ddos_block_ip(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 400
    assert "IP non valido" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_block_ip_success(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_request.form = AsyncMock(return_value={"ip": "1.2.3.4"})
    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    res = await security_ddos_block_ip(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "1.2.3.4/32 bloccato" in res.body.decode()
    mock_iptables.assert_called_once_with(["-I", "INPUT", "1", "-s", "1.2.3.4/32", "-j", "DROP"])


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_block_ip_failure(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_request.form = AsyncMock(return_value={"ip": "1.2.3.4"})
    mock_iptables = AsyncMock(return_value=False)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    res = await security_ddos_block_ip(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Impossibile bloccare 1.2.3.4" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_unblock_ip_unauthorized(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=None)
    )
    res = await security_ddos_unblock_ip(mock_request, mock_db)
    assert res.status_code == 401


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_unblock_ip_invalid(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_request.form = AsyncMock(return_value={"ip": "invalid_ip"})

    res = await security_ddos_unblock_ip(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 400
    assert "IP non valido" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_unblock_ip_success(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_request.form = AsyncMock(return_value={"ip": "1.2.3.4"})
    mock_iptables = AsyncMock(return_value=True)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    res = await security_ddos_unblock_ip(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "1.2.3.4 sbloccato" in res.body.decode() or "1.2.3.4/32 sbloccato" in res.body.decode()
    mock_iptables.assert_called_once_with(["-D", "INPUT", "-s", "1.2.3.4/32", "-j", "DROP"])


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_unblock_ip_failure(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_request.form = AsyncMock(return_value={"ip": "1.2.3.4"})
    mock_iptables = AsyncMock(return_value=False)
    monkeypatch.setattr("pit_panel.web.routes.security_ddos._iptables", mock_iptables)

    res = await security_ddos_unblock_ip(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Regola non trovata per 1.2.3.4/32" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_top_connections_unauthorized(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=None)
    )
    res = await security_ddos_top_connections(mock_request, mock_db)
    assert res.status_code == 401


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_top_connections_empty(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    mock_run_cmd.return_value.stdout = (
        "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
    )
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await security_ddos_top_connections(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Nessuna connessione attiva rilevata." in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_top_connections_with_data(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    mock_run_cmd.return_value.stdout = (
        "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        "ESTAB 0      0      10.0.0.1:80      192.168.1.100:12345 \n"
        "ESTAB 0      0      10.0.0.1:80      192.168.1.100:12346 \n"
        "ESTAB 0      0      10.0.0.1:443     10.0.0.5:54321 \n"
        "ESTAB 0      0      127.0.0.1:8080   127.0.0.1:56789 \n"
    )
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await security_ddos_top_connections(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "192.168.1.100" in res.body.decode()
    assert "2 conn" in res.body.decode()
    assert "10.0.0.5" in res.body.decode()
    assert "1 conn" in res.body.decode()
    assert "127.0.0.1" not in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_ddos_top_connections_fallback(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    mock_run_cmd = AsyncMock()
    mock_run_cmd.side_effect = [
        MagicMock(returncode=1),
        MagicMock(
            returncode=0,
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
            "ESTAB 0 0 10.0.0.1:80 192.168.1.100:12345\n",
        ),
    ]
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    res = await security_ddos_top_connections(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "192.168.1.100" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_protect_all_unauthorized(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=None)
    )
    res = await security_protect_all(mock_request, mock_db)
    assert res.status_code == 401


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_protect_all_success(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("pit_panel.core.security._get_client_ip", MagicMock(return_value="1.2.3.4"))
    monkeypatch.setattr("pit_panel.core.security._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.core.security._enable_ufw", AsyncMock(return_value=True))

    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._enable_shield", AsyncMock(return_value=[])
    )

    res = await security_protect_all(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Firewall UFW attivato" in res.body.decode()
    assert "Fail2ban: sshd attivo" in res.body.decode()
    assert "Fail2ban: sshd-ddos attivo" in res.body.decode()
    assert "Anti-DDoS Shield attivato" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_protect_all_partial_failure(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("pit_panel.core.security._get_client_ip", MagicMock(return_value="1.2.3.4"))
    monkeypatch.setattr("pit_panel.core.security._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.core.security._enable_ufw", AsyncMock(return_value=False))

    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 1
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=False)
    )

    res = await security_protect_all(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Firewall: errore" in res.body.decode()
    assert "Fail2ban: sshd non disponibile" in res.body.decode()
    assert "Anti-DDoS: iptables non nei sudoers" in res.body.decode()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_security_protect_all_shield_with_errors(
    mock_request: Request, mock_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos.get_admin", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("pit_panel.core.security._get_client_ip", MagicMock(return_value="1.2.3.4"))
    monkeypatch.setattr("pit_panel.core.security._detect_ssh_port", AsyncMock(return_value=22))
    monkeypatch.setattr("pit_panel.core.security._enable_ufw", AsyncMock(return_value=True))

    mock_run_cmd = AsyncMock()
    mock_run_cmd.return_value.returncode = 0
    monkeypatch.setattr("pit_panel.web.routes.security_ddos.run_cmd", mock_run_cmd)

    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._ensure_sudoers", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "pit_panel.web.routes.security_ddos._enable_shield", AsyncMock(return_value=["error1"])
    )

    res = await security_protect_all(mock_request, mock_db)
    assert isinstance(res, HTMLResponse)
    assert res.status_code == 200
    assert "Anti-DDoS Shield attivato (con avvisi)" in res.body.decode()

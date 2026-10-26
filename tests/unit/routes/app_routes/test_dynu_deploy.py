from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from pit_panel.web.routes.app_routes.deploy import (
    _allocate_host_port,
    _resolve_subdomain,
    _stop_git_process,
)


@pytest.mark.asyncio
async def test_resolve_subdomain_uses_dynu_effective_domain():
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    settings = SimpleNamespace(
        base_domain="",
        dynu_domain="root.dynu.net",
        effective_domain="root.dynu.net",
    )
    sd, error = await _resolve_subdomain(db, 7, settings, False, -1, "customer")
    assert error is None
    assert sd.base_domain == "root.dynu.net"


@pytest.mark.asyncio
async def test_resolve_subdomain_requires_admin_for_new_dynu_record():
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    settings = SimpleNamespace(
        base_domain="example.test",
        dynu_domain="root.dynu.net",
        dynu_api_key="secret",
        effective_domain="root.dynu.net",
    )
    sd, error = await _resolve_subdomain(db, 7, settings, False, -1, "customer", False)
    assert sd is None
    assert error == "Administrator privileges required"


@pytest.mark.asyncio
async def test_resolve_subdomain_rejects_custom_name_owned_by_another_user():
    db = AsyncMock()
    existing = SimpleNamespace(owner_user_id=99, app_type=None)
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
    settings = SimpleNamespace(base_domain="example.test", effective_domain="example.test")
    sd, error = await _resolve_subdomain(db, 7, settings, False, -1, "customer", False)
    assert sd is existing
    assert error == "You do not own this subdomain"


@pytest.mark.asyncio
async def test_host_port_allocator_rejects_panel_port_and_existing_reservation():
    db = AsyncMock()
    db.execute.return_value = MagicMock(
        scalars=MagicMock(first=MagicMock(return_value=None))
    )
    settings = SimpleNamespace(port=8080)
    with pytest.raises(ValueError, match="panel port"):
        await _allocate_host_port(db, 8080, settings)
    db.execute.return_value = MagicMock(scalars=MagicMock(first=MagicMock(return_value=1)))
    with pytest.raises(ValueError, match="already reserved"):
        await _allocate_host_port(db, 8081, settings)


@pytest.mark.asyncio
async def test_host_port_allocator_blocks_the_neighbouring_port():
    """A WordPress app also binds PORT+1, so the neighbour must stay free."""
    db = AsyncMock()
    settings = SimpleNamespace(port=8080)

    captured = {}

    async def execute(query):
        captured["query"] = query
        return MagicMock(scalars=MagicMock(first=MagicMock(return_value=8000)))

    db.execute = execute

    with pytest.raises(ValueError, match="already reserved"):
        await _allocate_host_port(db, 8001, settings)

    sql = str(captured["query"].compile(compile_kwargs={"literal_binds": True}))
    assert "8000" in sql and "8001" in sql and "8002" in sql


@pytest.mark.asyncio
async def test_stop_git_process_terminates_and_drains_child():
    proc = MagicMock(returncode=None)
    proc.communicate = AsyncMock(side_effect=[TimeoutError(), (b"", b"")])
    await _stop_git_process(proc)
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()

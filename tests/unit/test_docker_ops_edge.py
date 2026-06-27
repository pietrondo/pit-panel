from unittest.mock import AsyncMock, patch

import pytest

from pit_panel.core.docker_ops import DockerManager


@pytest.fixture
def mock_proc():
    proc = AsyncMock()
    proc.communicate.return_value = (b"stdout_mock", b"stderr_mock")
    proc.returncode = 0
    return proc


@pytest.mark.asyncio
async def test_run_compose_command_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.run_compose_command("test_app", ["up", "-d"])
        assert result["success"] is False
        assert "Docker not found" in result["error"]


@pytest.mark.asyncio
async def test_compose_ps_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.compose_ps("test_app")
        assert result == []


@pytest.mark.asyncio
async def test_compose_logs_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.compose_logs("test_app")
        assert "Failed to retrieve logs" in result


@pytest.mark.asyncio
async def test_ps_all_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.ps_all()
        assert result == []


@pytest.mark.asyncio
async def test_container_stop_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.container_stop("abc123")
        assert result["success"] is False
        assert "Docker not found" in result["error"]


@pytest.mark.asyncio
async def test_container_start_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.container_start("abc123")
        assert result["success"] is False
        assert "Docker not found" in result["error"]


@pytest.mark.asyncio
async def test_container_stats_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.container_stats("abc123")
        assert result == {}


@pytest.mark.asyncio
async def test_container_logs_live_oserror():
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Docker not found")):
        result = await manager.container_logs_live("abc123")
        assert "Failed to retrieve container logs" in result

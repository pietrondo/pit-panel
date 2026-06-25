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
async def test_compose_up_success(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_up("test_app")
        mock_exec.assert_called_once()
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_compose_up_failure(mock_proc):
    mock_proc.returncode = 1
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_up("test_app")
        mock_exec.assert_called_once()
        assert result == {"success": False, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_compose_down_success(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_down("test_app")
        mock_exec.assert_called_once()
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_compose_restart_success(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_restart("test_app")
        mock_exec.assert_called_once()
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_compose_ps(mock_proc):
    manager = DockerManager()
    mock_proc.communicate.return_value = (b'{"name": "test1"}\n{"name": "test2"}\n', b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_ps("test_app")
        mock_exec.assert_called_once()
        assert result == [{"name": "test1"}, {"name": "test2"}]


@pytest.mark.asyncio
async def test_compose_ps_invalid_json(mock_proc):
    manager = DockerManager()
    mock_proc.communicate.return_value = (
        b'{"name": "test1"}\ninvalid json\n{"name": "test2"}\n',
        b"",
    )
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_ps("test_app")
        mock_exec.assert_called_once()
        assert result == [{"name": "test1"}, {"name": "test2"}]


@pytest.mark.asyncio
async def test_compose_logs(mock_proc):
    manager = DockerManager()
    mock_proc.communicate.return_value = (b"log line 1\nlog line 2", b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_logs("test_app")
        mock_exec.assert_called_once()
        assert result == "log line 1\nlog line 2"

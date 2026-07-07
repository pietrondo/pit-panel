import asyncio
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
async def test_containers_count(mock_proc: AsyncMock) -> None:
    mgr = DockerManager()
    mock_proc.communicate.return_value = (b"running\nexited\nrunning\n", b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        total, running = await mgr.containers_count()
        assert total == 3
        assert running == 2
        mock_exec.assert_called_once()
        assert "docker" in mock_exec.call_args[0]
        assert "ps" in mock_exec.call_args[0]
        assert "{{.State}}" in mock_exec.call_args[0]


@pytest.mark.asyncio
async def test_containers_count_oserror(mock_proc: AsyncMock) -> None:
    mgr = DockerManager()
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Exec failed")):
        total, running = await mgr.containers_count()
        assert total == 0
        assert running == 0


@pytest.mark.asyncio
async def test_run_compose_command_up_success(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.run_compose_command("test_app", ["up", "-d"])
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "up",
            "-d",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_run_compose_command_up_failure(mock_proc):
    mock_proc.returncode = 1
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.run_compose_command("test_app", ["up", "-d"])
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "up",
            "-d",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == {"success": False, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_run_compose_command_down_success(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.run_compose_command("test_app", ["down"])
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "down",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_run_compose_command_restart_success(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.run_compose_command("test_app", ["restart"])
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "restart",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_compose_ps(mock_proc):
    manager = DockerManager()
    mock_proc.communicate.return_value = (b'{"name": "test1"}\n{"name": "test2"}\n', b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_ps("test_app")
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "ps",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
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
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "ps",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == [{"name": "test1"}, {"name": "test2"}]


@pytest.mark.asyncio
async def test_compose_logs(mock_proc):
    manager = DockerManager()
    mock_proc.communicate.return_value = (b"log line 1\nlog line 2", b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.compose_logs("test_app")
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "logs",
            "--tail",
            "100",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == "log line 1\nlog line 2"


@pytest.mark.asyncio
async def test_ps_all(mock_proc):
    manager = DockerManager()
    mock_proc.communicate.return_value = (
        b'{"ID":"abc123","Names":"my-nginx","State":"running","Status":"Up","Image":"nginx:alpine","Ports":"80/tcp"}\n'
        b'{"ID":"def456","Names":"my-app","State":"exited","Status":"Exited","Image":"python:3.12","Ports":"0.0.0.0:8000"}\n',
        b"",
    )
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.ps_all()
        mock_exec.assert_called_once_with(
            "docker",
            "ps",
            "-a",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    assert len(result) == 2
    assert result[0]["ID"] == "abc123"
    assert result[1]["State"] == "exited"


@pytest.mark.asyncio
async def test_container_stop(mock_proc):
    manager = DockerManager()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"abc123", b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.container_stop("abc123")
        mock_exec.assert_called_once_with(
            "docker",
            "stop",
            "abc123",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    assert result["success"] is True
    assert result["stdout"] == "abc123"


@pytest.mark.asyncio
async def test_container_start(mock_proc):
    manager = DockerManager()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"abc123", b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.container_start("abc123")
        mock_exec.assert_called_once_with(
            "docker",
            "start",
            "abc123",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_container_stats(mock_proc):
    manager = DockerManager()
    stats_json = (
        '{"CPUPerc":"0.50%","MemUsage":"50MiB / 1GiB","NetIO":"1kB / 2kB","BlockIO":"10MB / 20MB"}'
    )
    mock_proc.communicate.return_value = (stats_json.encode(), b"")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.container_stats("abc123")
        mock_exec.assert_called_once_with(
            "docker",
            "stats",
            "abc123",
            "--no-stream",
            "--format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    assert result["CPUPerc"] == "0.50%"


@pytest.mark.asyncio
async def test_container_logs_live(mock_proc):
    manager = DockerManager()
    mock_proc.communicate.return_value = (
        b"[2025-06-25T10:00:00Z] Started\n[2025-06-25T10:00:01Z] Ready\n",
        b"warning: deprecated",
    )
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.container_logs_live("abc123")
        mock_exec.assert_called_once_with(
            "docker",
            "logs",
            "abc123",
            "--tail",
            "100",
            "--timestamps",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    assert "[2025-06-25T10:00:00Z] Started" in result
    assert "warning: deprecated" in result


@pytest.mark.asyncio
async def test_exec_command_no_env(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.exec_command("test_app", "web", ["ls", "-l"])
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "exec",
            "-T",
            "web",
            "ls",
            "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}


@pytest.mark.asyncio
async def test_exec_command_with_env(mock_proc):
    manager = DockerManager()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await manager.exec_command(
            "test_app",
            "web",
            ["ls", "-l"],
            env={"VAR1": "val1", "VAR2": "val2"},
        )
        mock_exec.assert_called_once_with(
            "docker",
            "compose",
            "-f",
            str(manager.apps_dir / "test_app" / "docker-compose.yml"),
            "exec",
            "-T",
            "-e",
            "VAR1=val1",
            "-e",
            "VAR2=val2",
            "web",
            "ls",
            "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(manager.apps_dir / "test_app"),
        )
        assert result == {"success": True, "stdout": "stdout_mock", "stderr": "stderr_mock"}

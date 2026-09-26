import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from pit_panel.core.repo_detector import cleanup, clone_repo


@pytest.fixture
def mock_proc():
    proc = AsyncMock()
    proc.communicate.return_value = (b"stdout_mock", b"stderr_mock")
    proc.returncode = 0
    return proc


@pytest.mark.asyncio
async def test_clone_repo_timeout_stops_child_before_cleanup(tmp_path):
    destination = tmp_path / "clone"
    destination.mkdir()
    started = asyncio.Event()
    proc = Mock()

    async def communicate():
        started.set()
        await asyncio.Event().wait()

    proc.communicate = communicate
    proc.wait = AsyncMock()
    proc.returncode = None
    order = []
    original_wait_for = asyncio.wait_for

    async def short_wait_for(awaitable, timeout):
        return await original_wait_for(awaitable, timeout=0.01)

    proc.terminate.side_effect = lambda: order.append("terminate")
    proc.wait.side_effect = lambda: order.append("wait")
    real_cleanup = cleanup

    def record_cleanup(path):
        order.append("cleanup")
        real_cleanup(path)

    with (
        patch("tempfile.mkdtemp", return_value=str(destination)),
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("pit_panel.core.repo_detector.asyncio.wait_for", side_effect=short_wait_for),
        patch("pit_panel.core.repo_detector.cleanup", side_effect=record_cleanup),
        pytest.raises(ValueError, match="Git clone timed out for repository: http://test.url/"),
    ):
        await clone_repo("http://test.url/")
    assert started.is_set()
    proc.terminate.assert_called_once()
    assert order == ["terminate", "wait", "cleanup"]
    assert proc.wait.await_count >= 1
    assert not destination.exists()


@pytest.mark.asyncio
async def test_clone_repo_cancellation_stops_child_before_cleanup(tmp_path):
    destination = tmp_path / "clone"
    destination.mkdir()
    started = asyncio.Event()
    proc = Mock()

    async def communicate():
        started.set()
        await asyncio.Event().wait()

    proc.communicate = communicate
    proc.wait = AsyncMock()
    proc.returncode = None
    order = []
    proc.terminate.side_effect = lambda: order.append("terminate")

    async def wait():
        order.append("wait")

    proc.wait.side_effect = wait
    real_cleanup = cleanup

    def record_cleanup(path):
        order.append("cleanup")
        real_cleanup(path)

    with (
        patch("tempfile.mkdtemp", return_value=str(destination)),
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("pit_panel.core.repo_detector.cleanup", side_effect=record_cleanup),
    ):
        task = asyncio.create_task(clone_repo("http://test.url/"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    proc.terminate.assert_called_once()
    assert order == ["terminate", "wait", "cleanup"]
    assert not destination.exists()


@pytest.mark.asyncio
async def test_clone_repo_kills_child_when_terminate_wait_times_out(tmp_path):
    destination = tmp_path / "clone"
    destination.mkdir()
    proc = Mock()
    proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())
    proc.wait = AsyncMock(side_effect=[TimeoutError(), None])
    proc.returncode = None
    with (
        patch("tempfile.mkdtemp", return_value=str(destination)),
        patch("asyncio.create_subprocess_exec", return_value=proc),
        pytest.raises(asyncio.CancelledError),
    ):
        await clone_repo("http://test.url/")
    proc.kill.assert_called_once()
    assert proc.wait.await_count == 2
    assert not destination.exists()


@pytest.mark.asyncio
async def test_shutdown_error_preserves_timeout_and_cleans_destination(tmp_path):
    destination = tmp_path / "clone"
    destination.mkdir()
    started = asyncio.Event()
    proc = Mock()

    async def communicate():
        started.set()
        await asyncio.Event().wait()

    proc.communicate = communicate
    proc.terminate.side_effect = RuntimeError("shutdown failed")
    proc.returncode = None
    original_wait_for = asyncio.wait_for

    async def short_wait_for(awaitable, timeout):
        return await original_wait_for(awaitable, timeout=0.01)

    real_cleanup = cleanup
    cleaned = []

    def record_cleanup(path):
        cleaned.append(path)
        real_cleanup(path)

    with (
        patch("tempfile.mkdtemp", return_value=str(destination)),
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("pit_panel.core.repo_detector.asyncio.wait_for", side_effect=short_wait_for),
        patch("pit_panel.core.repo_detector.cleanup", side_effect=record_cleanup),
        pytest.raises(ValueError, match="Git clone timed out for repository: http://test.url/"),
    ):
        await clone_repo("http://test.url/")
    assert cleaned == [destination]
    assert not destination.exists()


def test_cleanup_logs_rmtree_oserror():
    fake_path = Path("/tmp/fake_repo")
    with (
        patch("shutil.rmtree", side_effect=OSError("Permission denied")),
        patch("pit_panel.core.repo_detector.logger.warning") as mock_logger,
    ):
        cleanup(fake_path)
    mock_logger.assert_called_once_with(f"Failed to cleanup {fake_path}: Permission denied")


@pytest.mark.asyncio
async def test_terminate_error_uses_kill_and_preserves_clone_timeout(tmp_path):
    destination = tmp_path / "clone"
    destination.mkdir()
    started = asyncio.Event()
    order = []
    proc = Mock()

    async def communicate():
        started.set()
        await asyncio.Event().wait()

    async def wait():
        order.append("wait")

    proc.communicate = communicate
    proc.terminate.side_effect = RuntimeError("terminate failed")
    proc.kill.side_effect = lambda: order.append("kill")
    proc.wait = AsyncMock(side_effect=wait)
    proc.returncode = None
    original_wait_for = asyncio.wait_for

    async def short_wait_for(awaitable, timeout):
        return await original_wait_for(awaitable, timeout=0.01)

    real_cleanup = cleanup

    def record_cleanup(path):
        order.append("cleanup")
        real_cleanup(path)

    with (
        patch("tempfile.mkdtemp", return_value=str(destination)),
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("pit_panel.core.repo_detector.asyncio.wait_for", side_effect=short_wait_for),
        patch("pit_panel.core.repo_detector.cleanup", side_effect=record_cleanup),
        pytest.raises(ValueError, match="Git clone timed out for repository: http://test.url/"),
    ):
        await clone_repo("http://test.url/")
    assert started.is_set()
    assert order == ["kill", "wait", "cleanup"]
    proc.kill.assert_called_once()
    assert not destination.exists()


@pytest.mark.asyncio
async def test_clone_repo_oserror(tmp_path):
    destination = tmp_path / "clone"
    destination.mkdir()
    with (
        patch("tempfile.mkdtemp", return_value=str(destination)),
        patch("asyncio.create_subprocess_exec", side_effect=OSError("No git executable")),
        pytest.raises(
            ValueError, match="Git executable not found or inaccessible: No git executable"
        ),
    ):
        await clone_repo("http://test.url/")
    assert not destination.exists()


@pytest.mark.asyncio
async def test_clone_repo_nonzero_exit(mock_proc, tmp_path):
    mock_proc.returncode = 1
    destination = tmp_path / "clone"
    destination.mkdir()
    with (
        patch("tempfile.mkdtemp", return_value=str(destination)),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        pytest.raises(ValueError, match="Git clone failed: stderr_mock"),
    ):
        await clone_repo("http://test.url/")
    assert not destination.exists()


def test_cleanup_exception():
    fake_path = Path("/tmp/fake_repo")
    with (
        patch("shutil.rmtree", side_effect=Exception("Permission denied")),
        patch("pit_panel.core.repo_detector.logger.warning") as mock_logger,
    ):
        cleanup(fake_path)
        mock_logger.assert_called_once_with(f"Failed to cleanup {fake_path}: Permission denied")

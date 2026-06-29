from unittest.mock import AsyncMock, patch
import pytest

from pit_panel.core.repo_detector import clone_repo, cleanup
from pathlib import Path


@pytest.fixture
def mock_proc():
    proc = AsyncMock()
    proc.communicate.return_value = (b"stdout_mock", b"stderr_mock")
    proc.returncode = 0
    return proc


@pytest.mark.asyncio
async def test_clone_repo_timeout():
    with patch("asyncio.create_subprocess_exec", side_effect=TimeoutError("Timed out")):
        with pytest.raises(ValueError, match="Git clone timed out for repository: test_url"):
            await clone_repo("test_url")


@pytest.mark.asyncio
async def test_clone_repo_oserror():
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("No git executable")):
        with pytest.raises(ValueError, match="Git executable not found or inaccessible: No git executable"):
            await clone_repo("test_url")


@pytest.mark.asyncio
async def test_clone_repo_nonzero_exit(mock_proc):
    mock_proc.returncode = 1
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(ValueError, match="Git clone failed: stderr_mock"):
            await clone_repo("test_url")


def test_cleanup_exception():
    with patch("shutil.rmtree", side_effect=Exception("Permission denied")), \
         patch("pit_panel.core.repo_detector.logger.warning") as mock_logger:
        cleanup(Path("/tmp/fake_repo"))
        mock_logger.assert_called_once_with("Failed to cleanup /tmp/fake_repo: Permission denied")

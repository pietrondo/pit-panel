from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pit_panel.config import Settings
from pit_panel.core.updater import Updater
from pit_panel.db.models import UpdateHistory


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.git_branch = "main"
    return settings


@pytest.fixture
def updater(mock_settings):
    return Updater(mock_settings)


@pytest.mark.asyncio
async def test_check_for_updates_new_version(updater):
    with patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run:
        # fetch, rev-parse remote, rev-parse local
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(stdout="new_sha\n"),
            MagicMock(stdout="old_sha\n"),
        ]

        result = await updater.check_for_updates()

        assert result == "new_sha"
        assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_check_for_updates_up_to_date(updater):
    with patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(stdout="same_sha\n"),
            MagicMock(stdout="same_sha\n"),
        ]

        result = await updater.check_for_updates()

        assert result is None


@pytest.mark.asyncio
async def test_check_for_updates_fetch_fails(updater):
    with patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = MagicMock(returncode=1)

        result = await updater.check_for_updates()

        assert result is None
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_check_for_updates_no_remote_sha(updater):
    with patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(stdout="\n"),
        ]

        result = await updater.check_for_updates()

        assert result is None


@pytest.mark.asyncio
async def test_check_for_updates_exception(updater):
    with patch(
        "pit_panel.core.updater._run_cmd", side_effect=Exception("error"), new_callable=AsyncMock
    ):
        result = await updater.check_for_updates()

        assert result is None


@pytest.mark.asyncio
async def test_apply_update_success(updater):
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_db

    with (
        patch("pit_panel.core.updater.get_sessionmaker", return_value=mock_sessionmaker),
        patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run,
    ):
        # git rev-parse HEAD
        # git reset
        # uv sync
        # alembic upgrade
        mock_run.side_effect = [
            MagicMock(stdout="old_sha\n"),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]

        result = await updater.apply_update("new_sha")

        assert result is True
        assert mock_db.add.call_count == 1
        added_entry = mock_db.add.call_args[0][0]
        assert isinstance(added_entry, UpdateHistory)
        assert added_entry.version_from == "old_sha"
        assert added_entry.version_to == "new_sha"
        assert added_entry.status == "completed"
        assert mock_db.commit.call_count == 2
        assert mock_run.call_count == 4


@pytest.mark.asyncio
async def test_apply_update_failure(updater):
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_db

    with (
        patch("pit_panel.core.updater.get_sessionmaker", return_value=mock_sessionmaker),
        patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run,
    ):
        # git rev-parse HEAD
        # git reset (fails)
        mock_run.side_effect = [
            MagicMock(stdout="old_sha\n"),
            MagicMock(returncode=1),
        ]

        result = await updater.apply_update("new_sha")

        assert result is False
        assert mock_db.add.call_count == 1
        added_entry = mock_db.add.call_args[0][0]
        assert added_entry.status == "failed"
        assert mock_db.commit.call_count == 2
        assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_rollback_success(updater):
    with patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]

        result = await updater.rollback()

        assert result is True
        assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_rollback_git_fails(updater):
    with patch("pit_panel.core.updater._run_cmd", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = MagicMock(returncode=1)

        result = await updater.rollback()

        assert result is False
        assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_healthcheck_success(updater):
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        result = await updater.healthcheck()

        assert result is True
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_healthcheck_failure(updater):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("error")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await updater.healthcheck(retries=2, delay=0.1)

            assert result is False
            assert mock_get.call_count == 2


@pytest.mark.asyncio
async def test_run_cmd_success():
    from pit_panel.core.updater import _run_cmd
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"out", b"err"))
        mock_exec.return_value = mock_proc

        result = await _run_cmd(["echo", "hello"], timeout=5)

        assert result.returncode == 0
        assert result.stdout == "out"
        assert result.stderr == "err"


@pytest.mark.asyncio
async def test_run_cmd_timeout():
    from pit_panel.core.updater import _run_cmd
    import asyncio
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError("timeout"))
        mock_proc.kill = MagicMock()
        mock_exec.return_value = mock_proc

        result = await _run_cmd(["sleep", "10"], timeout=1)

        assert result.returncode == -1
        assert result.stdout == ""
        assert result.stderr == "Timeout"
        mock_proc.kill.assert_called_once()

@pytest.mark.asyncio
async def test_run_cmd_exception():
    from pit_panel.core.updater import _run_cmd
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = Exception("error")

        result = await _run_cmd(["invalid_command"], timeout=5)

        assert result.returncode == -1
        assert result.stdout == ""
        assert result.stderr == "error"

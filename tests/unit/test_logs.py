import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from pit_panel.web.routes.logs import _read_journal_sync, _read_log, applog_partial, journal_partial


@pytest.mark.asyncio
async def test_read_log_valid_file():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, newline="\n") as f:
        f.write("line 1\nline 2\n")
        path = f.name

    try:
        result = await _read_log(path)
        assert "line 1\nline 2" in result
    finally:
        os.remove(path)


@pytest.mark.asyncio
async def test_read_log_invalid_file():
    result = await _read_log("/path/that/does/not/exist.log")
    assert result == "[log file not found or inaccessible]"


@pytest.mark.asyncio
async def test_read_log_tail():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, newline="\n") as f:
        for i in range(10):
            f.write(f"line {i}\n")
        path = f.name

    try:
        result = await _read_log(path, tail=2)
        assert result == "line 8\nline 9\n"
    finally:
        os.remove(path)


def test_read_journal_sync_direct_success():
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.stdout = "Dec 10 12:00:00 pit-panel test log\n"
        mock_run.return_value = mock_proc

        res = _read_journal_sync(10)
        assert res == "Dec 10 12:00:00 pit-panel test log\n"
        mock_run.assert_called_once_with(
            ["journalctl", "-u", "pit-panel.service", "-n", "10", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )


def test_read_journal_sync_fallback_success():
    with patch("subprocess.run") as mock_run:

        def side_effect(args, **kwargs):
            if args[0] == "journalctl":
                raise subprocess.SubprocessError("Permission denied")
            mock_proc = MagicMock()
            mock_proc.stdout = "Dec 10 12:00:00 sudo pit-panel test log\n"
            return mock_proc

        mock_run.side_effect = side_effect

        res = _read_journal_sync(10)
        assert res == "Dec 10 12:00:00 sudo pit-panel test log\n"
        assert mock_run.call_count == 2


def test_read_journal_sync_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = Exception("failed")

        res = _read_journal_sync(10)
        assert res == "[journal unavailable — pit-panel user needs systemd-journal group]"


@pytest.mark.asyncio
async def test_journal_partial():
    with patch("pit_panel.web.routes.logs._read_journal") as mock_read:
        mock_read.return_value = "fake <log> data"
        request = MagicMock(spec=Request)
        response = await journal_partial(request)
        assert response.status_code == 200
        assert "<pre" in response.body.decode()
        assert "fake &lt;log&gt; data" in response.body.decode()


@pytest.mark.asyncio
async def test_applog_partial():
    with patch("pit_panel.web.routes.logs._read_log") as mock_read:
        mock_read.return_value = "fake app <log> data"
        request = MagicMock(spec=Request)
        response = await applog_partial(request)
        assert response.status_code == 200
        assert "<pre" in response.body.decode()
        assert "fake app &lt;log&gt; data" in response.body.decode()

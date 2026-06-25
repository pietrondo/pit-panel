import os
import tempfile

import pytest

from pit_panel.web.routes.logs import _read_log


@pytest.mark.asyncio
async def test_read_log_valid_file():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
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
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        for i in range(10):
            f.write(f"line {i}\n")
        path = f.name

    try:
        result = await _read_log(path, tail=2)
        assert result == "line 8\nline 9\n"
    finally:
        os.remove(path)

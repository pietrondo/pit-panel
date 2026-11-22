import asyncio

import pytest

from pit_panel.core.docker_ops import _communicate


class _HangingProc:
    def __init__(self) -> None:
        self.killed = False

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        await asyncio.sleep(5)
        return b"", b""

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return 0


@pytest.mark.asyncio
async def test_communicate_kills_a_hung_command():
    proc = _HangingProc()

    stdout, stderr = await _communicate(proc, 0.01)  # type: ignore[arg-type]

    assert stdout == b""
    assert b"timed out" in stderr
    assert proc.killed is True

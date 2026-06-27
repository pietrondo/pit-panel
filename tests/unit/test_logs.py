import os
import tempfile

import pytest

from pit_panel.web.routes.logs import _read_log


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


def test_journal_partial(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pit_panel.web.routes.logs import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    async def mock_read_journal(*args, **kwargs):
        return 'System message <script>alert("hacked")</script> &'

    monkeypatch.setattr("pit_panel.web.routes.logs._read_journal", mock_read_journal)

    resp = client.get("/logs/journal")
    assert resp.status_code == 200
    assert (
        "System message &lt;script&gt;alert(&quot;hacked&quot;)&lt;/script&gt; &amp;" in resp.text
    )
    assert '<pre class="text-xs font-mono text-green-400 whitespace-pre-wrap">' in resp.text


def test_applog_partial(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pit_panel.web.routes.logs import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    async def mock_read_log(*args, **kwargs):
        return "App message <div>test</div>"

    monkeypatch.setattr("pit_panel.web.routes.logs._read_log", mock_read_log)

    resp = client.get("/logs/applog")
    assert resp.status_code == 200
    assert "App message &lt;div&gt;test&lt;/div&gt;" in resp.text
    assert '<pre class="text-xs font-mono text-green-400 whitespace-pre-wrap">' in resp.text

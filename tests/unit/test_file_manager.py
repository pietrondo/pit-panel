import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.config import Settings, init_settings
from pit_panel.db.models import Base, User
from pit_panel.web.app import create_app
from pit_panel.web.routes.file_manager import verify_safe_path


@pytest.fixture
def client(monkeypatch):
    s = Settings(
        secret_key="test-secret-key-32chars!!",
        database_url="sqlite+aiosqlite://",
        debug=True,
    )
    init_settings()
    monkeypatch.setattr("pit_panel.config._settings", s)

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=None)

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    import asyncio
    asyncio.run(create_tables())

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("pit_panel.db.session._engine", engine)
    monkeypatch.setattr("pit_panel.db.session._sessionmaker", sessionmaker)

    app = create_app(s)
    return TestClient(app)

@pytest.fixture
def auth_headers(monkeypatch):
    async def mock_get_admin(*args, **kwargs):
        return User(id=1, username="admin", is_admin=True)

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)
    return {}

def test_path_validation():
    # Test valid paths
    temp_dir = tempfile.gettempdir()
    assert verify_safe_path(temp_dir) == Path(temp_dir).resolve()
    assert verify_safe_path(os.getcwd()) == Path(os.getcwd()).resolve()

    # Test path traversal attempts
    with pytest.raises(PermissionError):
        verify_safe_path("/etc/passwd")

    with pytest.raises(PermissionError):
        # Even if prepended by allowed root
        verify_safe_path(os.path.join(temp_dir, "../../../../../etc/passwd"))

def test_unauthenticated_access(client):
    # Verify redirects/401s for unauthenticated users
    r = client.get("/system/file-manager", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"

    r = client.get("/system/terminal", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"

    r = client.get("/api/file-manager/list")
    assert r.status_code == 401

    r = client.get("/api/file-manager/file?path=dummy")
    assert r.status_code == 401

    r = client.post(
        "/api/file-manager/save",
        json={"path": "dummy", "content": "dummy"}
    )
    assert r.status_code == 401

    r = client.post(
        "/api/file-manager/create",
        json={"parent_path": "dummy", "name": "dummy", "type": "file"}
    )
    assert r.status_code == 401

    r = client.post("/api/file-manager/delete", json={"path": "dummy"})
    assert r.status_code == 401

    r = client.post(
        "/api/file-manager/upload",
        data={"parent_path": "dummy"},
        files={"file": ("test.txt", b"content")}
    )
    assert r.status_code == 401

def test_list_files(client, auth_headers):
    temp_dir = tempfile.gettempdir()
    r = client.get(f"/api/file-manager/list?path={temp_dir}")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert "items" in data
    assert "path" in data

def test_file_crud_operations(client, auth_headers):
    # Create a temporary file to test file operations
    temp_dir = tempfile.gettempdir()
    test_file_path = os.path.join(temp_dir, "pit_panel_test_crud.txt")

    if os.path.exists(test_file_path):
        os.unlink(test_file_path)

    # 1. Create file via endpoint
    r = client.post("/api/file-manager/create", json={
        "parent_path": temp_dir,
        "name": "pit_panel_test_crud.txt",
        "type": "file"
    })
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    assert os.path.exists(test_file_path)

    # 2. Save content to file
    r = client.post("/api/file-manager/save", json={
        "path": test_file_path,
        "content": "hello file manager!"
    })
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    # 3. Read content from file
    r = client.get(f"/api/file-manager/file?path={test_file_path}")
    assert r.status_code == 200
    data = r.json()
    assert data["content"] == "hello file manager!"

    # 4. Delete file
    r = client.post("/api/file-manager/delete", json={
        "path": test_file_path
    })
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    assert not os.path.exists(test_file_path)

def test_create_directory_and_upload(client, auth_headers):
    temp_dir = tempfile.gettempdir()
    test_sub_dir = os.path.join(temp_dir, "pit_panel_test_dir")

    if os.path.exists(test_sub_dir):
        shutil.rmtree(test_sub_dir)

    # Create directory
    r = client.post("/api/file-manager/create", json={
        "parent_path": temp_dir,
        "name": "pit_panel_test_dir",
        "type": "directory"
    })
    assert r.status_code == 200
    assert os.path.exists(test_sub_dir)

    # Upload file to that directory
    r = client.post("/api/file-manager/upload", data={
        "parent_path": test_sub_dir
    }, files={
        "file": ("upload.txt", b"uploaded content")
    })
    assert r.status_code == 200

    uploaded_file_path = os.path.join(test_sub_dir, "upload.txt")
    assert os.path.exists(uploaded_file_path)
    with open(uploaded_file_path, "rb") as f:
        assert f.read() == b"uploaded content"

    # Cleanup
    shutil.rmtree(test_sub_dir)

def test_websocket_terminal_unauthorized(client):
    # If not authorized, WS should be closed/rejected
    with client.websocket_connect("/system/terminal/ws") as ws:
        msg = ws.receive_text()
        assert "Unauthorized" in msg
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()

def test_websocket_terminal_authorized(client, monkeypatch):
    # Mock WebSocket authentication to return True
    async def mock_check_ws_admin(*args, **kwargs):
        return True
    monkeypatch.setattr("pit_panel.web.routes.file_manager.check_ws_admin", mock_check_ws_admin)

    # Mock subprocess execution
    class MockProcess:
        def __init__(self):
            self.returncode = None
            self.stdin = MagicMock()
            self.stdin.write = MagicMock()
            self.stdin.drain = AsyncMock()
            self.stdout = AsyncMock()
            self.stderr = AsyncMock()

            # Setup mock read side_effects
            self.stdout.read = AsyncMock(side_effect=[b"terminal_welcome_message\n", b""])
            self.stderr.read = AsyncMock(return_value=b"")

        async def wait(self):
            self.returncode = 0
            return 0

        def terminate(self):
            self.returncode = 0

        def kill(self):
            self.returncode = 0

    mock_proc = MockProcess()

    async def mock_create_subprocess_exec(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)

    # Test WebSocket connection
    with client.websocket_connect("/system/terminal/ws") as ws:
        # Receive welcome message
        msg = ws.receive_text()
        assert "terminal_welcome_message" in msg

        # Send command input
        ws.send_text("echo test\n")

        # Wait for the async loop to process and write the text
        import time
        for _ in range(20):
            if mock_proc.stdin.write.called:
                break
            time.sleep(0.05)

        # Check that stdin.write was called with command input
        assert mock_proc.stdin.write.called

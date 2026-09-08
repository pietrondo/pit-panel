from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pit_panel.web.routes.file_manager import verify_safe_path


def test_verify_safe_path_valid():
    # Assume CWD is allowed
    cwd = Path.cwd()
    assert verify_safe_path(str(cwd)) == cwd


def test_verify_safe_path_invalid():
    with pytest.raises(PermissionError):
        verify_safe_path("/root")


class MockUser:
    def __init__(self):
        self.username = "admin"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_file_manager_page(mock_get_admin):
    mock_get_admin.return_value = MockUser()
    from fastapi import Request

    from pit_panel.web.routes.file_manager import file_manager_page

    req = MagicMock(spec=Request)
    req.url = MagicMock()
    req.url.path = "/system/file-manager"
    res = await file_manager_page(req, db=MagicMock())
    assert res.status_code == 200


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_system_terminal_page(mock_get_admin):
    mock_get_admin.return_value = MockUser()
    from fastapi import Request

    from pit_panel.web.routes.file_manager import system_terminal_page

    req = MagicMock(spec=Request)
    req.url = MagicMock()
    req.url.path = "/system/terminal"
    res = await system_terminal_page(req, db=MagicMock())
    assert res.status_code == 200


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_list_files(mock_get_admin, tmp_path):
    mock_get_admin.return_value = MockUser()
    from pit_panel.web.routes.file_manager import ALLOWED_ROOTS, list_files

    if tmp_path not in ALLOWED_ROOTS:
        ALLOWED_ROOTS.append(tmp_path)

    (tmp_path / "test_file.txt").touch()

    res = await list_files(str(tmp_path), request=MagicMock(), db=MagicMock())
    assert res["status"] == "success"
    assert len(res["items"]) == 1
    assert res["items"][0]["name"] == "test_file.txt"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_list_files_unauthorized(mock_get_admin):
    mock_get_admin.return_value = None
    from fastapi import HTTPException

    from pit_panel.web.routes.file_manager import list_files

    with pytest.raises(HTTPException) as excinfo:
        await list_files("/some/path", request=MagicMock(), db=MagicMock())
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_list_files_permission_denied(mock_get_admin):
    mock_get_admin.return_value = MockUser()
    from fastapi import HTTPException

    from pit_panel.web.routes.file_manager import list_files

    with pytest.raises(HTTPException) as excinfo:
        await list_files("/root", request=MagicMock(), db=MagicMock())
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_get_file_content(mock_get_admin, tmp_path):
    mock_get_admin.return_value = MockUser()
    from pit_panel.web.routes.file_manager import ALLOWED_ROOTS, get_file_content

    if tmp_path not in ALLOWED_ROOTS:
        ALLOWED_ROOTS.append(tmp_path)

    test_file = tmp_path / "test_read.txt"
    test_file.write_text("hello world")

    from fastapi import Request

    req = MagicMock(spec=Request)
    req.url = MagicMock()
    req.url.path = "/api/file-manager/read"

    res = await get_file_content(str(test_file), request=req, db=MagicMock())
    assert type(res) == dict
    assert res.get("content") == "hello world"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_save_file(mock_get_admin, tmp_path):
    mock_get_admin.return_value = MockUser()
    # It's better to test save_file with TestClient because of the limiter
    from fastapi import FastAPI, Request

    from pit_panel.web.routes.file_manager import router

    app = FastAPI()
    app.include_router(router)

    from pit_panel.web.routes.file_manager import ALLOWED_ROOTS

    if tmp_path not in ALLOWED_ROOTS:
        ALLOWED_ROOTS.append(tmp_path)

    test_file = tmp_path / "test_write.txt"
    test_file.touch()

    with patch("pit_panel.web.routes.file_manager.limiter.limit", return_value=lambda x: x):
        import importlib

        import pit_panel.web.routes.file_manager

        importlib.reload(pit_panel.web.routes.file_manager)

        # We also need to patch get_admin inside the reloaded module
        with patch("pit_panel.web.routes.file_manager.get_admin", return_value=MockUser()):
            from pit_panel.web.routes.file_manager import ALLOWED_ROOTS, SaveFileRequest

            if tmp_path not in ALLOWED_ROOTS:
                ALLOWED_ROOTS.append(tmp_path)

            req = SaveFileRequest(path=str(test_file), content="new content")
            http_req = MagicMock(spec=Request)
            http_req.url = MagicMock()
            http_req.url.path = "/api/file-manager/save"
            http_req.client = MagicMock()
            http_req.client.host = "127.0.0.1"

            res = await pit_panel.web.routes.file_manager.save_file(
                req=req, request=http_req, db=MagicMock()
            )
            assert res["status"] == "success"
            assert test_file.read_text() == "new content"


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_create_resource(mock_get_admin, tmp_path):
    mock_get_admin.return_value = MockUser()
    from pit_panel.web.routes.file_manager import (
        ALLOWED_ROOTS,
        CreateResourceRequest,
        create_resource,
    )

    if tmp_path not in ALLOWED_ROOTS:
        ALLOWED_ROOTS.append(tmp_path)

    req = CreateResourceRequest(parent_path=str(tmp_path), name="new_folder", type="directory")
    res = await create_resource(req, request=MagicMock(), db=MagicMock())

    assert res["status"] == "success"
    assert (tmp_path / "new_folder").is_dir()

    req_file = CreateResourceRequest(parent_path=str(tmp_path), name="new_file.txt", type="file")
    res_file = await create_resource(req_file, request=MagicMock(), db=MagicMock())

    assert res_file["status"] == "success"
    assert (tmp_path / "new_file.txt").is_file()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_delete_resource(mock_get_admin, tmp_path):
    mock_get_admin.return_value = MockUser()
    from pit_panel.web.routes.file_manager import (
        ALLOWED_ROOTS,
        DeleteResourceRequest,
        delete_resource,
    )

    if tmp_path not in ALLOWED_ROOTS:
        ALLOWED_ROOTS.append(tmp_path)

    test_file = tmp_path / "test_delete.txt"
    test_file.touch()

    req = DeleteResourceRequest(path=str(test_file))
    res = await delete_resource(req, request=MagicMock(), db=MagicMock())

    assert res["status"] == "success"
    assert not test_file.exists()


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.get_admin")
async def test_upload_file(mock_get_admin, tmp_path):
    mock_get_admin.return_value = MockUser()

    from fastapi import UploadFile

    from pit_panel.web.routes.file_manager import ALLOWED_ROOTS, upload_file

    if tmp_path not in ALLOWED_ROOTS:
        ALLOWED_ROOTS.append(tmp_path)

    file_content = b"upload test"
    upload_mock = MagicMock(spec=UploadFile)
    upload_mock.filename = "uploaded.txt"

    # We need to mock await file.read()
    async def mock_read(size=-1):
        if hasattr(mock_read, "called"):
            return b""
        mock_read.called = True
        return file_content

    upload_mock.read = mock_read

    res = await upload_file(
        parent_path=str(tmp_path), file=upload_mock, request=MagicMock(), db=MagicMock()
    )

    assert res["status"] == "success"
    assert (tmp_path / "uploaded.txt").read_bytes() == file_content


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.check_ws_admin")
async def test_terminal_ws_unauthorized(mock_check_ws_admin):
    mock_check_ws_admin.return_value = False
    from pit_panel.web.routes.file_manager import terminal_ws

    ws_mock = MagicMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_text = AsyncMock()
    ws_mock.close = AsyncMock()

    await terminal_ws(ws_mock, db=MagicMock())

    ws_mock.accept.assert_called_once()
    ws_mock.send_text.assert_called_once()
    ws_mock.close.assert_called_once_with(code=1008)


@pytest.mark.asyncio
@patch("pit_panel.web.routes.file_manager.check_ws_admin")
async def test_terminal_ws_authorized_mock(mock_check_ws_admin):
    mock_check_ws_admin.return_value = True

    from pit_panel.web.routes.file_manager import terminal_ws

    ws_mock = MagicMock()
    ws_mock.accept = AsyncMock()
    ws_mock.receive_text = AsyncMock(side_effect=["ls -la\r", Exception("break")])
    ws_mock.send_text = AsyncMock()
    ws_mock.close = AsyncMock()

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc_mock = MagicMock()
        proc_mock.stdin = AsyncMock()
        proc_mock.stdin.write = MagicMock()
        proc_mock.stdin.drain = AsyncMock()
        proc_mock.stdout = AsyncMock()
        proc_mock.stdout.read = AsyncMock(side_effect=[b"output", b""])
        proc_mock.stderr = AsyncMock()
        proc_mock.stderr.read = AsyncMock(side_effect=[b""])
        proc_mock.returncode = None
        proc_mock.terminate = MagicMock()
        proc_mock.wait = AsyncMock()
        mock_exec.return_value = proc_mock

        await terminal_ws(ws_mock, db=MagicMock())

        ws_mock.accept.assert_called_once()
        # Should have attempted to create a subprocess
        mock_exec.assert_called()
        proc_mock.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_check_ws_admin(monkeypatch):
    from pit_panel.web.auth import SESSION_COOKIE
    from pit_panel.web.routes.file_manager import check_ws_admin

    ws_mock = MagicMock()
    ws_mock.cookies = {}
    ws_mock.headers = {}

    # Test no cookie
    assert not await check_ws_admin(ws_mock, db=MagicMock())

    # Test cookie in header
    ws_mock.headers = {"cookie": f"{SESSION_COOKIE}=test_token"}

    # Mock settings and token logic
    mock_settings = MagicMock()
    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_settings", lambda: mock_settings)
    monkeypatch.setattr(
        "pit_panel.web.routes.file_manager.unsign_session_token", lambda s, c: {"uid": 1}
    )

    async def mock_validate(*args, **kwargs):
        user = MagicMock()
        user.is_admin = True
        return user

    monkeypatch.setattr("pit_panel.web.routes.file_manager.validate_session", mock_validate)

    assert await check_ws_admin(ws_mock, db=MagicMock())


@pytest.mark.asyncio
async def test_file_manager_page_unauthorized(monkeypatch):
    from fastapi import Request

    from pit_panel.web.routes.file_manager import file_manager_page

    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)

    req = MagicMock(spec=Request)
    res = await file_manager_page(req, db=MagicMock())
    assert res.status_code == 302
    assert res.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_system_terminal_page_unauthorized(monkeypatch):
    from fastapi import Request

    from pit_panel.web.routes.file_manager import system_terminal_page

    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)

    req = MagicMock(spec=Request)
    res = await system_terminal_page(req, db=MagicMock())
    assert res.status_code == 302
    assert res.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_get_file_content_unauthorized(monkeypatch):
    from fastapi import HTTPException

    from pit_panel.web.routes.file_manager import get_file_content

    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)

    with pytest.raises(HTTPException) as excinfo:
        await get_file_content("/some/path", request=MagicMock(), db=MagicMock())
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_get_file_content_permission_denied(monkeypatch):
    from fastapi import HTTPException

    from pit_panel.web.routes.file_manager import get_file_content

    async def mock_get_admin(*args, **kwargs):
        return MockUser()

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)

    with pytest.raises(HTTPException) as excinfo:
        await get_file_content("/root/secret", request=MagicMock(), db=MagicMock())
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_create_resource_unauthorized(monkeypatch):
    from fastapi import HTTPException

    from pit_panel.web.routes.file_manager import CreateResourceRequest, create_resource

    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)

    req = CreateResourceRequest(parent_path="/tmp", name="new", type="file")
    with pytest.raises(HTTPException) as excinfo:
        await create_resource(req, request=MagicMock(), db=MagicMock())
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_delete_resource_unauthorized(monkeypatch):
    from fastapi import HTTPException

    from pit_panel.web.routes.file_manager import DeleteResourceRequest, delete_resource

    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)

    req = DeleteResourceRequest(path="/tmp/test")
    with pytest.raises(HTTPException) as excinfo:
        await delete_resource(req, request=MagicMock(), db=MagicMock())
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_upload_file_unauthorized(monkeypatch):
    from fastapi import HTTPException

    from pit_panel.web.routes.file_manager import upload_file

    async def mock_get_admin(*args, **kwargs):
        return None

    monkeypatch.setattr("pit_panel.web.routes.file_manager.get_admin", mock_get_admin)

    with pytest.raises(HTTPException) as excinfo:
        await upload_file(parent_path="/tmp", file=MagicMock(), request=MagicMock(), db=MagicMock())
    assert excinfo.value.status_code == 401

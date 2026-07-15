"""File Manager and System Terminal routes."""

import asyncio
import contextlib
import os
import platform
import shutil
import tempfile
from pathlib import Path

if platform.system() != "Windows":
    import fcntl
    import pty


from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import get_settings
from pit_panel.db.session import get_db
from pit_panel.web.auth import SESSION_COOKIE, unsign_session_token, validate_session
from pit_panel.web.deps import get_admin
from pit_panel.web.limiter import limiter
from pit_panel.web.render import render

router = APIRouter()

ALLOWED_ROOTS = [
    Path("/opt/pit-panel"),
    Path("/etc/pit-panel"),
    Path("/var/lib/pit-panel"),
    Path(os.getcwd()).resolve(),
    Path(tempfile.gettempdir()).resolve(),
]


def verify_safe_path(path_str: str) -> Path:
    if not path_str:
        raise PermissionError("Empty path")
    # First resolve path
    p = Path(path_str).resolve()

    # Check against allowed roots
    for root in ALLOWED_ROOTS:
        try:
            resolved_root = root.resolve()
            if p == resolved_root or p.is_relative_to(resolved_root):
                return p
        except ValueError:
            continue
    raise PermissionError("Path access denied: outside allowed directories")


async def check_ws_admin(websocket: WebSocket, db: AsyncSession) -> bool:
    cookie = websocket.cookies.get(SESSION_COOKIE)
    if not cookie:
        cookie_header = websocket.headers.get("cookie", "")
        if cookie_header:
            from http.cookies import SimpleCookie

            c = SimpleCookie()
            c.load(cookie_header)
            if SESSION_COOKIE in c:
                cookie = c[SESSION_COOKIE].value
    if not cookie:
        return False
    try:
        settings = get_settings()
        data = unsign_session_token(settings, cookie)
        if not data:
            return False
        uid = data.get("uid")
        if uid is None:
            return False
        user = await validate_session(db, cookie, settings, uid, data=data)
        return user is not None and user.is_admin
    except Exception:
        return False


class SaveFileRequest(BaseModel):
    path: str
    content: str


class CreateResourceRequest(BaseModel):
    parent_path: str
    name: str
    type: str  # "file" or "directory"


class DeleteResourceRequest(BaseModel):
    path: str


@router.get("/system/file-manager", response_class=HTMLResponse)
async def file_manager_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render("file_manager.html", request=request, user=user, title="File Manager")


@router.get("/system/terminal", response_class=HTMLResponse)
async def system_terminal_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render("system_terminal.html", request=request, user=user, title="System Terminal")


@router.get("/api/file-manager/list")
async def list_files(
    path: str | None = None, request: Request = None, db: AsyncSession = Depends(get_db)
):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not path:
        path = "/opt/pit-panel" if os.path.exists("/opt/pit-panel") else os.getcwd()

    try:
        resolved_path = verify_safe_path(path)
        if not resolved_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")

        items = []
        for entry in resolved_path.iterdir():
            try:
                stat = entry.stat()
                permissions = oct(stat.st_mode & 0o777)
                items.append(
                    {
                        "name": entry.name,
                        "path": str(entry.absolute()),
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size if not entry.is_dir() else 0,
                        "mtime": stat.st_mtime,
                        "permissions": permissions,
                    }
                )
            except Exception:
                continue
        return {"status": "success", "path": str(resolved_path), "items": items}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/file-manager/file")
async def get_file_content(path: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        resolved_path = verify_safe_path(path)
        if not resolved_path.is_file():
            raise HTTPException(status_code=400, detail="Not a file")
        content = resolved_path.read_text(encoding="utf-8", errors="replace")
        return {"content": content, "path": str(resolved_path)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/file-manager/save")
@limiter.limit("20/minute")
async def save_file(req: SaveFileRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        resolved_path = verify_safe_path(req.path)
        resolved_path.write_text(req.content, encoding="utf-8")
        return {"status": "success", "message": "File saved successfully"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/file-manager/create")
async def create_resource(
    req: CreateResourceRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        resolved_parent = verify_safe_path(req.parent_path)
        target_path = resolved_parent / req.name
        resolved_target = verify_safe_path(str(target_path))

        if req.type == "directory":
            resolved_target.mkdir(parents=True, exist_ok=True)
        else:
            resolved_target.touch()
        return {"status": "success", "message": f"{req.type.capitalize()} created successfully"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/file-manager/delete")
async def delete_resource(
    req: DeleteResourceRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        resolved_path = verify_safe_path(req.path)
        if resolved_path.is_dir():
            shutil.rmtree(resolved_path)
        else:
            resolved_path.unlink()
        return {"status": "success", "message": "Resource deleted successfully"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/file-manager/upload")
async def upload_file(
    parent_path: str = Form(...),
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        resolved_parent = verify_safe_path(parent_path)
        filename = os.path.basename(file.filename)
        target_path = resolved_parent / filename
        resolved_target = verify_safe_path(str(target_path))

        def _save_file() -> None:
            with open(resolved_target, "wb") as f:
                shutil.copyfileobj(file.file, f)

        await asyncio.to_thread(_save_file)

        return {"status": "success", "message": "File uploaded successfully"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.websocket("/system/terminal/ws")
async def terminal_ws(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    await websocket.accept()

    is_admin = await check_ws_admin(websocket, db)
    if not is_admin:
        await websocket.send_text("\r\nUnauthorized: Admin access required.\r\n")
        await websocket.close(code=1008)
        return

    # Determine platform and PTY availability
    is_windows = platform.system() == "Windows"
    use_pty = not is_windows

    master_fd = None
    slave_fd = None

    if use_pty:
        try:
            master_fd, slave_fd = pty.openpty()
            # Set non-blocking
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except Exception:
            use_pty = False
            if master_fd is not None:
                with contextlib.suppress(Exception):
                    os.close(master_fd)
                master_fd = None
            if slave_fd is not None:
                with contextlib.suppress(Exception):
                    os.close(slave_fd)
                slave_fd = None

    shell = "powershell.exe" if is_windows else "/bin/bash"
    proc = None
    try:
        if use_pty:
            proc = await asyncio.create_subprocess_exec(
                shell,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                shell,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
    except Exception as e:
        fallback_shell = "cmd.exe" if is_windows else "sh"
        try:
            if use_pty:
                proc = await asyncio.create_subprocess_exec(
                    fallback_shell,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    preexec_fn=os.setsid,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    fallback_shell,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
        except Exception as ex:
            if use_pty:
                if master_fd is not None:
                    with contextlib.suppress(Exception):
                        os.close(master_fd)
                if slave_fd is not None:
                    with contextlib.suppress(Exception):
                        os.close(slave_fd)
            await websocket.send_text(f"\r\nFailed to start shell: {e} / {ex}\r\n")
            await websocket.close()
            return

    # Close slave_fd in the parent process as the child handles it now
    if use_pty and slave_fd is not None:
        with contextlib.suppress(Exception):
            os.close(slave_fd)
        slave_fd = None

    # Detect mock process (unit tests)
    is_mock = False
    if proc is not None:
        stdin_type = type(getattr(proc, "stdin", None)).__name__
        proc_type = type(proc).__name__
        if "Mock" in stdin_type or "Mock" in proc_type:
            is_mock = True

    if is_mock and use_pty:
        use_pty = False
        if master_fd is not None:
            with contextlib.suppress(Exception):
                os.close(master_fd)
            master_fd = None

    if use_pty:
        # PTY mode (Linux / macOS)
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def read_callback():
            try:
                data = os.read(master_fd, 4096)
                if not data:
                    queue.put_nowait(None)
                    with contextlib.suppress(Exception):
                        loop.remove_reader(master_fd)
                else:
                    queue.put_nowait(data)
            except OSError:
                queue.put_nowait(None)
                with contextlib.suppress(Exception):
                    loop.remove_reader(master_fd)
            except Exception:
                queue.put_nowait(None)
                with contextlib.suppress(Exception):
                    loop.remove_reader(master_fd)

        loop.add_reader(master_fd, read_callback)

        async def send_to_websocket():
            try:
                while True:
                    data = await queue.get()
                    if data is None:
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
            except Exception:
                pass
            finally:
                with contextlib.suppress(Exception):
                    await websocket.close()

        send_task = asyncio.create_task(send_to_websocket())

        try:
            while True:
                message = await websocket.receive_text()
                if proc.returncode is not None:
                    break
                os.write(master_fd, message.encode("utf-8"))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            with contextlib.suppress(Exception):
                loop.remove_reader(master_fd)
            if master_fd is not None:
                with contextlib.suppress(Exception):
                    os.close(master_fd)
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    with contextlib.suppress(Exception):
                        proc.kill()
            send_task.cancel()
            await asyncio.gather(send_task, return_exceptions=True)
            with contextlib.suppress(Exception):
                await websocket.close()

    else:
        # standard pipe mode (Windows, or testing fallback)
        async def read_from_stdout():
            try:
                while True:
                    data = await proc.stdout.read(4096)
                    if not data:
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
            except Exception:
                pass

        async def read_from_stderr():
            try:
                while True:
                    data = await proc.stderr.read(4096)
                    if not data:
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
            except Exception:
                pass

        stdout_task = asyncio.create_task(read_from_stdout())
        stderr_task = asyncio.create_task(read_from_stderr())

        try:
            while True:
                message = await websocket.receive_text()
                if proc.returncode is not None:
                    break
                # Windows fallback handles carriage returns and echoes locally if not mocked
                if is_windows and not is_mock:
                    if message == "\r":
                        await websocket.send_text("\r\n")
                        proc.stdin.write(b"\n")
                    else:
                        await websocket.send_text(message)
                        proc.stdin.write(message.encode("utf-8"))
                else:
                    proc.stdin.write(message.encode("utf-8"))
                await proc.stdin.drain()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    with contextlib.suppress(Exception):
                        proc.kill()
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            with contextlib.suppress(Exception):
                await websocket.close()

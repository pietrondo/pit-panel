from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.cli.admin import create_admin, reset_password
from pit_panel.db.models import Base, User


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    yield sessionmaker
    await engine.dispose()


@pytest.fixture
def mock_settings(settings):
    with patch("pit_panel.cli.admin.Settings.from_config_file", return_value=settings):
        yield settings


@pytest.mark.asyncio
async def test_create_admin_success(memory_db, mock_settings, capsys):
    with (
        patch("pit_panel.cli.admin.get_sessionmaker", return_value=memory_db),
        patch("pit_panel.cli.admin.init_db", new_callable=AsyncMock),
    ):
        await create_admin("admin", "password123", "admin@example.com")

        # Verify user was created
        async with memory_db() as db:
            result = await db.execute(select(User).where(User.username == "admin"))
            user = result.scalar_one_or_none()
            assert user is not None
            assert user.username == "admin"
            assert user.email == "admin@example.com"
            assert user.is_admin is True
            assert user.password_hash != "password123"  # Should be hashed

        # Verify output
        captured = capsys.readouterr()
        assert "Admin user 'admin' created." in captured.out


@pytest.mark.asyncio
async def test_create_admin_already_exists(memory_db, mock_settings, capsys):
    with (
        patch("pit_panel.cli.admin.get_sessionmaker", return_value=memory_db),
        patch("pit_panel.cli.admin.init_db", new_callable=AsyncMock),
    ):
        # Pre-create user
        async with memory_db() as db:
            user = User(
                username="existing", email="old@example.com", password_hash="hash", is_admin=False
            )
            db.add(user)
            await db.commit()

        await create_admin("existing", "newpass", "new@example.com")

        # Verify user was not modified
        async with memory_db() as db:
            result = await db.execute(select(User).where(User.username == "existing"))
            user = result.scalar_one_or_none()
            assert user.email == "old@example.com"
            assert user.is_admin is False

        # Verify output
        captured = capsys.readouterr()
        assert "User 'existing' already exists." in captured.out


@pytest.mark.asyncio
async def test_reset_password_success(memory_db, mock_settings, capsys):
    with patch("pit_panel.cli.admin.get_sessionmaker", return_value=memory_db):
        # Pre-create user
        async with memory_db() as db:
            user = User(
                username="target",
                email="target@example.com",
                password_hash="oldhash",
                is_admin=False,
            )
            db.add(user)
            await db.commit()

        await reset_password("target", "newpassword123")

        # Verify password was changed
        async with memory_db() as db:
            result = await db.execute(select(User).where(User.username == "target"))
            user = result.scalar_one_or_none()
            assert user.password_hash != "oldhash"
            assert user.password_hash != "newpassword123"  # Should be hashed

        # Verify output
        captured = capsys.readouterr()
        assert "Password for 'target' reset." in captured.out


@pytest.mark.asyncio
async def test_reset_password_not_found(memory_db, mock_settings, capsys):
    with patch("pit_panel.cli.admin.get_sessionmaker", return_value=memory_db):
        await reset_password("nonexistent", "newpassword123")

        # Verify output
        captured = capsys.readouterr()
        assert "User 'nonexistent' not found." in captured.out


def test_main_create_admin():
    with (
        patch(
            "sys.argv",
            [
                "admin.py",
                "create-admin",
                "--username",
                "testuser",
                "--password",
                "testpass",
                "--email",
                "test@example.com",
            ],
        ),
        patch("pit_panel.cli.admin.create_admin", new_callable=MagicMock) as mock_create_admin,
        patch("asyncio.run") as mock_run,
    ):
        from pit_panel.cli.admin import main

        main()

        mock_create_admin.assert_called_once_with("testuser", "testpass", "test@example.com")
        mock_run.assert_called_once_with(mock_create_admin.return_value)


def test_main_reset_password():
    with (
        patch(
            "sys.argv",
            ["admin.py", "reset-password", "--username", "testuser", "--password", "newpass"],
        ),
        patch("pit_panel.cli.admin.reset_password", new_callable=MagicMock) as mock_reset_password,
        patch("asyncio.run") as mock_run,
    ):
        from pit_panel.cli.admin import main

        main()

        mock_reset_password.assert_called_once_with("testuser", "newpass")
        mock_run.assert_called_once_with(mock_reset_password.return_value)


def test_main_no_args(capsys):
    with patch("sys.argv", ["admin.py"]), pytest.raises(SystemExit) as exc_info:
        from pit_panel.cli.admin import main

        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "usage:" in captured.out or "usage:" in captured.err

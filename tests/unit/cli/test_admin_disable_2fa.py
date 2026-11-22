from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pit_panel.cli.admin import disable_2fa
from pit_panel.db.models import Base, User


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    yield sessionmaker
    await engine.dispose()


@pytest.mark.asyncio
async def test_disable_2fa_clears_secret(memory_db, capsys):
    with patch("pit_panel.cli.admin.get_sessionmaker", return_value=memory_db):
        async with memory_db() as db:
            db.add(
                User(
                    username="admin",
                    email="a@example.com",
                    password_hash="hash",
                    totp_secret="JBSWY3DPEHPK3PXP",
                    totp_enabled=True,
                )
            )
            await db.commit()

        await disable_2fa("admin")

        async with memory_db() as db:
            result = await db.execute(select(User).where(User.username == "admin"))
            user = result.scalar_one()
            assert user.totp_enabled is False
            assert user.totp_secret is None

        assert "2FA disabled for 'admin'." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_disable_2fa_unknown_user(memory_db, capsys):
    with patch("pit_panel.cli.admin.get_sessionmaker", return_value=memory_db):
        await disable_2fa("ghost")
        assert "User 'ghost' not found." in capsys.readouterr().out

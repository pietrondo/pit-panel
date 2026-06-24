import pytest


class TestModels:
    @pytest.mark.asyncio
    async def test_create_tables(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base, User

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            user = User(username="test", email="test@test.com", password_hash="hash", is_admin=True)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            assert user.id is not None
            assert user.username == "test"
            assert user.is_admin

    @pytest.mark.asyncio
    async def test_audit_log(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import AuditLog, Base

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            entry = AuditLog(
                action="test_action",
                target_type="test",
                target_id=1,
                details={"key": "value"},
                ip="127.0.0.1",
            )
            db.add(entry)
            await db.commit()
            await db.refresh(entry)
            assert entry.action == "test_action"
            assert entry.details == {"key": "value"}

    @pytest.mark.asyncio
    async def test_subdomain_relationships(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from pit_panel.db.models import Base, Subdomain, User

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as db:
            user = User(username="owner", email="o@o.com", password_hash="h", is_admin=True)
            db.add(user)
            await db.flush()

            sd = Subdomain(subdomain="test", base_domain="example.com", owner_user_id=user.id)
            db.add(sd)
            await db.commit()
            await db.refresh(sd)

            assert sd.subdomain == "test"
            assert sd.base_domain == "example.com"
            assert sd.owner_user_id == user.id

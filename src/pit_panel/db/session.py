from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pit_panel.config import Settings

_engine = None
_sessionmaker = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine
    if _engine is None:
        if settings is None:
            settings = Settings()
        _engine = create_async_engine(
            settings.get_database_url(),
            echo=settings.debug,
        )
    return _engine


def get_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        engine = get_engine(settings)
        _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


async def init_db(settings: Settings) -> None:
    from pit_panel.db.models import Base

    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Migration v4: add is_main_domain column (separate transaction)
    async with engine.begin() as conn:
        import sqlalchemy as sa

        result = await conn.execute(sa.text("PRAGMA table_info(subdomains)"))
        columns = [r[1] for r in result.fetchall()]
        if "is_main_domain" not in columns:
            await conn.execute(
                sa.text("ALTER TABLE subdomains ADD COLUMN is_main_domain INTEGER DEFAULT 0")
            )

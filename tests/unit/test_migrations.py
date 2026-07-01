"""Tests for DB schema migrations/initialization."""

import pytest
import sqlalchemy as sa


@pytest.mark.asyncio
async def test_init_db_creates_is_main_domain_column(tmp_path):
    """init_db creates subdomains table with is_main_domain column."""
    import pit_panel.db.session as db_session
    from pit_panel.config import Settings

    db_session._engine = None
    db_path = str(tmp_path / "test.db")
    s = Settings(secret_key="test", database_url=f"sqlite+aiosqlite:///{db_path}")

    try:
        # Run init_db
        await db_session.init_db(s)
        engine = db_session.get_engine(s)

        # Verify column exists
        def check_after(c):
            cols = [r[1] for r in c.execute(sa.text("PRAGMA table_info(subdomains)")).fetchall()]
            assert "is_main_domain" in cols

        async with engine.connect() as conn:
            await conn.run_sync(check_after)

    finally:
        db_session._engine = None
        # Disposing if engine is not None
        if "engine" in locals() and engine is not None:
            await engine.dispose()

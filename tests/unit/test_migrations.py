"""Tests for DB schema migrations."""
import pytest
import sqlalchemy as sa


@pytest.mark.asyncio
async def test_migration_v4_adds_column(tmp_path):
    """init_db adds is_main_domain to existing subdomains table."""
    import pit_panel.db.session as db_session
    from pit_panel.config import Settings

    db_session._engine = None
    db_path = str(tmp_path / "test.db")
    s = Settings(secret_key="test", database_url=f"sqlite+aiosqlite:///{db_path}")
    engine = db_session.get_engine(s)

    try:
        # Create table WITHOUT is_main_domain
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: c.execute(
                    sa.text(
                        "CREATE TABLE subdomains ("
                        "id INTEGER PRIMARY KEY, "
                        "subdomain VARCHAR(64), "
                        "base_domain VARCHAR(256), "
                        "owner_user_id INTEGER, "
                        "app_type VARCHAR(32), "
                        "status VARCHAR(16) DEFAULT 'active', "
                        "created_at DATETIME, "
                        "last_deployed DATETIME)"
                    )
                )
            )

        # Verify column missing
        def check_before(c):
            cols = [r[1] for r in c.execute(  # noqa: E501
                sa.text("PRAGMA table_info(subdomains)")
            ).fetchall()]
            assert "is_main_domain" not in cols
        async with engine.connect() as conn:
            await conn.run_sync(check_before)

        # Run init_db (includes migration)
        db_session._engine = None
        await db_session.init_db(s)
        engine = db_session.get_engine(s)

        # Verify column exists
        def check_after(c):
            cols = [r[1] for r in c.execute(  # noqa: E501
                sa.text("PRAGMA table_info(subdomains)")
            ).fetchall()]
            assert "is_main_domain" in cols
        async with engine.connect() as conn:
            await conn.run_sync(check_after)

        # Verify default value
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: c.execute(
                    sa.text(
                        "INSERT INTO subdomains "
                        "(subdomain, base_domain, owner_user_id) "
                        "VALUES ('test', 'example.com', 1)"
                    )
                )
            )
        def check_default(c):
            rows = c.execute(
                sa.text("SELECT is_main_domain FROM subdomains")
            ).fetchall()
            assert rows[0][0] == 0
        async with engine.connect() as conn:
            await conn.run_sync(check_default)
    finally:
        db_session._engine = None
        await engine.dispose()


@pytest.mark.asyncio
async def test_migration_v4_idempotent(tmp_path):
    """init_db running twice doesn't cause errors."""
    import pit_panel.db.session as db_session
    from pit_panel.config import Settings

    db_session._engine = None
    db_path = str(tmp_path / "test.db")
    s = Settings(secret_key="test", database_url=f"sqlite+aiosqlite:///{db_path}")
    engine = db_session.get_engine(s)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: c.execute(
                    sa.text(
                        "CREATE TABLE subdomains ("
                        "id INTEGER PRIMARY KEY, "
                        "subdomain VARCHAR(64), "
                        "base_domain VARCHAR(256), "
                        "owner_user_id INTEGER, "
                        "app_type VARCHAR(32), "
                        "status VARCHAR(16) DEFAULT 'active', "
                        "created_at DATETIME, "
                        "last_deployed DATETIME)"
                    )
                )
            )

        db_session._engine = None
        await db_session.init_db(s)
        db_session._engine = None
        await db_session.init_db(s)

        engine = db_session.get_engine(s)
        def check(c):
            cols = [r[1] for r in c.execute(  # noqa: E501
                sa.text("PRAGMA table_info(subdomains)")
            ).fetchall()]
            assert "is_main_domain" in cols
        async with engine.connect() as conn:
            await conn.run_sync(check)
    finally:
        db_session._engine = None
        await engine.dispose()

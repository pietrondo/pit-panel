"""Tests for DB schema migrations."""

import os
import tempfile

import pytest
import sqlalchemy as sa


def _create_old_subdomains(conn):
    conn.execute(
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


@pytest.mark.asyncio
async def test_migration_v4_adds_is_main_domain():
    """Verify _migrate_v4_is_main_domain adds the column to an existing subdomains table."""
    import pit_panel.db.session as db_session
    from pit_panel.config import Settings
    from pit_panel.db.session import _migrate_v4_is_main_domain

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db_session._engine = None
        s = Settings(secret_key="test", database_url=f"sqlite+aiosqlite:///{db_path}")
        engine = db_session.get_engine(s)

        # Create subdomains table WITHOUT is_main_domain (simulate old DB)
        async with engine.begin() as conn:
            await conn.run_sync(_create_old_subdomains)

        # Verify column does NOT exist initially
        async with engine.connect() as conn:
            def check_before(c):
                cols = [r[1] for r in c.execute(sa.text("PRAGMA table_info(subdomains)")).fetchall()]  # noqa: E501
                assert "is_main_domain" not in cols
            await conn.run_sync(check_before)

        # Run migration
        async with engine.begin() as conn:
            await conn.run_sync(_migrate_v4_is_main_domain)

        # Verify column was added
        async with engine.connect() as conn:
            def check_after(c):
                cols = [r[1] for r in c.execute(sa.text("PRAGMA table_info(subdomains)")).fetchall()]  # noqa: E501
                assert "is_main_domain" in cols
            await conn.run_sync(check_after)

        # Verify query with is_main_domain works
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: c.execute(
                    sa.text("INSERT INTO subdomains (subdomain, base_domain, owner_user_id) VALUES ('test', 'example.com', 1)")  # noqa: E501
                )
            )
        async with engine.connect() as conn:
            def check_query(c):
                rows = c.execute(sa.text("SELECT is_main_domain FROM subdomains")).fetchall()
                assert rows[0][0] == 0  # DEFAULT 0
            await conn.run_sync(check_query)

    finally:
        db_session._engine = None
        await engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_migration_v4_idempotent():
    """Verify running migration twice doesn't cause errors."""
    import pit_panel.db.session as db_session
    from pit_panel.config import Settings
    from pit_panel.db.session import _migrate_v4_is_main_domain

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db_session._engine = None
        s = Settings(secret_key="test", database_url=f"sqlite+aiosqlite:///{db_path}")
        engine = db_session.get_engine(s)

        # Create table WITHOUT the column
        async with engine.begin() as conn:
            await conn.run_sync(_create_old_subdomains)

        async with engine.begin() as conn:
            await conn.run_sync(_migrate_v4_is_main_domain)

        # Second run should be idempotent
        async with engine.begin() as conn:
            await conn.run_sync(_migrate_v4_is_main_domain)

        async with engine.connect() as conn:
            def check(c):
                cols = [r[1] for r in c.execute(sa.text("PRAGMA table_info(subdomains)")).fetchall()]  # noqa: E501
                assert "is_main_domain" in cols
                assert len(cols) == 9
            await conn.run_sync(check)

    finally:
        db_session._engine = None
        await engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)

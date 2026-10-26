"""Reconcile an existing SQLite database with the current models.

``Base.metadata.create_all`` only creates missing *tables*: a column added to a
model after the table exists is never created, so a deploy that adds a column
leaves the panel querying a schema it does not have. That is what made the
Dynu deploy answer 500 on every page that selects a subdomain.

The panel keeps its schema with ``create_all`` rather than with alembic (the
migrations were never applied by the deploy script), so the same step also
adds the missing columns and indexes. Anything SQLite cannot do with
``ALTER TABLE ADD COLUMN`` is reported instead of silently skipped.
"""

from __future__ import annotations

import logging

from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from pit_panel.db.models import Base

logger = logging.getLogger(__name__)


def _columns(connection: Connection, table_name: str) -> set[str]:
    rows = connection.exec_driver_sql(f'PRAGMA table_info("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def _table_names(connection: Connection) -> set[str]:
    rows = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _index_names(connection: Connection, table_name: str) -> set[str]:
    rows = connection.exec_driver_sql(f'PRAGMA index_list("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def _missing(connection: Connection, *, include_tables: bool) -> list[str]:
    """Column names the models expect and the database does not have."""
    present_tables = _table_names(connection)
    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in present_tables:
            if include_tables:
                missing.append(f"{table.name}.*")
            continue
        present = _columns(connection, table.name)
        missing.extend(
            f"{table.name}.{column.name}"
            for column in table.columns
            if column.name not in present
        )
    return missing


async def missing_columns(engine: AsyncEngine) -> list[str]:
    """Report model columns (and tables) the database does not have, without changing it."""
    if engine.dialect.name != "sqlite":
        return []
    async with engine.connect() as conn:
        return await conn.run_sync(lambda c: _missing(c, include_tables=True))


async def sync_schema(engine: AsyncEngine) -> list[str]:
    """Add the missing columns and indexes. Returns the list of added columns."""
    if engine.dialect.name != "sqlite":
        return []

    added: list[str] = []
    async with engine.begin() as conn:
        present_tables = await conn.run_sync(_table_names)
        for table in Base.metadata.sorted_tables:
            if table.name not in present_tables:
                continue
            present = await conn.run_sync(_columns, table.name)
            for column in table.columns:
                if column.name in present:
                    continue
                if not column.nullable and column.server_default is None:
                    logger.error(
                        "Cannot add NOT NULL column %s.%s without a server default",
                        table.name,
                        column.name,
                    )
                    continue
                column_type = column.type.compile(conn.dialect)
                await conn.exec_driver_sql(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'
                )
                added.append(f"{table.name}.{column.name}")

        for table in Base.metadata.sorted_tables:
            if table.name not in present_tables or not table.indexes:
                continue
            existing = await conn.run_sync(_index_names, table.name)
            for index in table.indexes:
                if index.name in existing:
                    continue
                await conn.run_sync(lambda c, i=index: i.create(c))

    if added:
        logger.warning("Schema reconciled: added %s", ", ".join(added))
    return added

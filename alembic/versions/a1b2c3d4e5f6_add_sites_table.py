"""Add sites table for site builder

Revision ID: a1b2c3d4e5f6
Revises: eed3ced4d83f
Create Date: 2026-08-13 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "eed3ced4d83f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("subdomain", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("widgets_json", sqlite.JSON(), nullable=False),
        sa.Column("published_html_path", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subdomain"),
    )
    op.create_index(op.f("ix_sites_owner_user_id"), "sites", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_sites_subdomain"), "sites", ["subdomain"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sites_subdomain"), table_name="sites")
    op.drop_index(op.f("ix_sites_owner_user_id"), table_name="sites")
    op.drop_table("sites")

"""Track Dynu records owned by subdomains.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subdomains", sa.Column("dynu_record_id", sa.Integer(), nullable=True))
    op.add_column("subdomains", sa.Column("dynu_ipv4", sa.String(length=45), nullable=True))
    op.add_column("subdomains", sa.Column("host_port", sa.Integer(), nullable=True))
    op.create_index("ix_subdomains_host_port", "subdomains", ["host_port"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_subdomains_host_port", table_name="subdomains")
    op.drop_column("subdomains", "dynu_ipv4")
    op.drop_column("subdomains", "host_port")
    op.drop_column("subdomains", "dynu_record_id")

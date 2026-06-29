"""Initial migration

Revision ID: eed3ced4d83f
Revises:
Create Date: 2026-06-27 22:28:21.297849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision: str = 'eed3ced4d83f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('login_attempts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('attempted_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_login_attempts_attempted_at'), 'login_attempts', ['attempted_at'], unique=False)
    op.create_index(op.f('ix_login_attempts_ip_address'), 'login_attempts', ['ip_address'], unique=False)
    op.create_table('malware_scans',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('target', sa.String(length=128), nullable=False),
    sa.Column('scan_type', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('infected_count', sa.Integer(), nullable=False),
    sa.Column('scanned_count', sa.Integer(), nullable=False),
    sa.Column('details', sqlite.JSON(), nullable=True),
    sa.Column('started_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_malware_scans_target'), 'malware_scans', ['target'], unique=False)
    op.create_table('update_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('version_from', sa.String(length=64), nullable=True),
    sa.Column('version_to', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('rollback_reason', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=256), nullable=False),
    sa.Column('password_hash', sa.String(length=256), nullable=False),
    sa.Column('totp_secret', sa.String(length=64), nullable=True),
    sa.Column('totp_enabled', sa.Boolean(), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_login', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target_type', sa.String(length=32), nullable=True),
    sa.Column('target_id', sa.Integer(), nullable=True),
    sa.Column('details', sqlite.JSON(), nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('timestamp', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_timestamp'), 'audit_log', ['timestamp'], unique=False)
    op.create_table('ip_bans',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=False),
    sa.Column('reason', sa.String(length=256), nullable=False),
    sa.Column('banned_by', sa.Integer(), nullable=True),
    sa.Column('banned_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('failed_attempts', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['banned_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ip_bans_ip_address'), 'ip_bans', ['ip_address'], unique=True)
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_token_hash'), 'sessions', ['token_hash'], unique=True)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('subdomains',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('subdomain', sa.String(length=64), nullable=False),
    sa.Column('base_domain', sa.String(length=256), nullable=False),
    sa.Column('owner_user_id', sa.Integer(), nullable=False),
    sa.Column('app_type', sa.String(length=32), nullable=True),
    sa.Column('is_main_domain', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('last_deployed', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subdomains_owner_user_id'), 'subdomains', ['owner_user_id'], unique=False)
    op.create_table('system_settings',
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('value', sqlite.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('app_deployments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('subdomain_id', sa.Integer(), nullable=False),
    sa.Column('stack_type', sa.String(length=32), nullable=False),
    sa.Column('compose_path', sa.String(length=512), nullable=False),
    sa.Column('env_path', sa.String(length=512), nullable=True),
    sa.Column('container_ids', sqlite.JSON(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['subdomain_id'], ['subdomains.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_app_deployments_subdomain_id'), 'app_deployments', ['subdomain_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_app_deployments_subdomain_id'), table_name='app_deployments')
    op.drop_table('app_deployments')
    op.drop_table('system_settings')
    op.drop_index(op.f('ix_subdomains_owner_user_id'), table_name='subdomains')
    op.drop_table('subdomains')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_token_hash'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_ip_bans_ip_address'), table_name='ip_bans')
    op.drop_table('ip_bans')
    op.drop_index(op.f('ix_audit_log_timestamp'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    op.drop_table('update_history')
    op.drop_index(op.f('ix_malware_scans_target'), table_name='malware_scans')
    op.drop_table('malware_scans')
    op.drop_index(op.f('ix_login_attempts_ip_address'), table_name='login_attempts')
    op.drop_index(op.f('ix_login_attempts_attempted_at'), table_name='login_attempts')
    op.drop_table('login_attempts')

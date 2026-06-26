import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    is_admin: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete")
    subdomains: Mapped[list["Subdomain"]] = relationship(
        back_populates="owner", cascade="all, delete"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Subdomain(Base):
    __tablename__ = "subdomains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subdomain: Mapped[str] = mapped_column(String(64), nullable=False)
    base_domain: Mapped[str] = mapped_column(String(256), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    app_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_main_domain: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    last_deployed: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="subdomains")
    deployments: Mapped[list["AppDeployment"]] = relationship(
        back_populates="subdomain", cascade="all, delete"
    )


class AppDeployment(Base):
    __tablename__ = "app_deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subdomain_id: Mapped[int] = mapped_column(
        ForeignKey("subdomains.id", ondelete="CASCADE"), index=True
    )
    stack_type: Mapped[str] = mapped_column(String(32), nullable=False)
    compose_path: Mapped[str] = mapped_column(String(512), nullable=False)
    env_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    container_ids: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    subdomain: Mapped["Subdomain"] = relationship(back_populates="deployments")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )


class UpdateHistory(Base):
    __tablename__ = "update_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="started")
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SystemSettings(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class MalwareScan(Base):
    __tablename__ = "malware_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scan_type: Mapped[str] = mapped_column(String(16), default="full")
    status: Mapped[str] = mapped_column(String(16), default="running")
    infected_count: Mapped[int] = mapped_column(Integer, default=0)
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class IPBan(Base):
    __tablename__ = "ip_bans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(256), default="auto")
    banned_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    banned_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    success: Mapped[bool] = mapped_column(default=False)
    attempted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )

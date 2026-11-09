"""Master database models: dioceses, parishes, tenant mapping, platform users, subscriptions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, MasterBase, StandardMixin, TimestampMixin, utcnow


class DioceseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ParishStatus(StrEnum):
    PROVISIONING = "PROVISIONING"
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class _AddressMixin:
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100), default="India")
    postal_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))


class Diocese(StandardMixin, _AddressMixin, MasterBase):
    __tablename__ = "dioceses"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    bishop_name: Mapped[str | None] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DioceseStatus.ACTIVE, index=True)

    parishes: Mapped[list[Parish]] = relationship(back_populates="diocese")


class Parish(StandardMixin, _AddressMixin, MasterBase):
    __tablename__ = "parishes"

    diocese_id: Mapped[int] = mapped_column(ForeignKey("dioceses.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    subdomain: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ParishStatus.PROVISIONING, index=True
    )
    established_on: Mapped[date | None] = mapped_column(Date)

    diocese: Mapped[Diocese] = relationship(back_populates="parishes")
    database: Mapped[TenantDatabase | None] = relationship(back_populates="parish", uselist=False)
    settings: Mapped[TenantSettings | None] = relationship(back_populates="parish", uselist=False)


class TenantDatabase(IdMixin, TimestampMixin, MasterBase):
    __tablename__ = "tenant_databases"

    parish_id: Mapped[int] = mapped_column(ForeignKey("parishes.id"), unique=True, nullable=False)
    db_host: Mapped[str] = mapped_column(String(255), nullable=False)
    db_port: Mapped[int] = mapped_column(Integer, nullable=False, default=3306)
    db_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    db_user: Mapped[str | None] = mapped_column(String(64))
    db_password_enc: Mapped[bytes | None] = mapped_column(LargeBinary(512))
    schema_version: Mapped[str | None] = mapped_column(String(64))
    last_migrated_at: Mapped[datetime | None] = mapped_column(DateTime())
    last_error: Mapped[str | None] = mapped_column(Text)

    parish: Mapped[Parish] = relationship(back_populates="database")


class TenantSettings(TimestampMixin, MasterBase):
    __tablename__ = "tenant_settings"

    parish_id: Mapped[int] = mapped_column(ForeignKey("parishes.id"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    primary_color: Mapped[str | None] = mapped_column(String(9))
    default_language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    fy_start_month: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=4)

    parish: Mapped[Parish] = relationship(back_populates="settings")


class Plan(IdMixin, TimestampMixin, MasterBase):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    max_families: Mapped[int | None] = mapped_column(Integer)
    max_users: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Subscription(IdMixin, TimestampMixin, MasterBase):
    __tablename__ = "subscriptions"

    parish_id: Mapped[int] = mapped_column(ForeignKey("parishes.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    trial_ends_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class PlatformUser(StandardMixin, MasterBase):
    __tablename__ = "platform_users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime())
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime())

    diocese_scopes: Mapped[list[DioceseUserScope]] = relationship(cascade="all, delete-orphan")


class DioceseUserScope(IdMixin, MasterBase):
    __tablename__ = "diocese_user_scopes"
    __table_args__ = (UniqueConstraint("platform_user_id", "diocese_id"),)

    platform_user_id: Mapped[int] = mapped_column(ForeignKey("platform_users.id"), nullable=False)
    diocese_id: Mapped[int] = mapped_column(ForeignKey("dioceses.id"), nullable=False)


class ParishStatsSnapshot(IdMixin, MasterBase):
    __tablename__ = "parish_stats_snapshots"
    __table_args__ = (UniqueConstraint("parish_id", "snapshot_date"),)

    parish_id: Mapped[int] = mapped_column(ForeignKey("parishes.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    families: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class PlatformAuditLog(IdMixin, MasterBase):
    __tablename__ = "platform_audit_logs"

    occurred_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(BigIntPK)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(26))
    parish_id: Mapped[int | None] = mapped_column(BigIntPK, index=True)
    ip: Mapped[str | None] = mapped_column(String(45))
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    remarks: Mapped[str | None] = mapped_column(Text)


class GlobalSetting(MasterBase):
    __tablename__ = "global_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)

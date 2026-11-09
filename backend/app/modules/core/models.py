"""Parish-database platform tables: settings, sequences, audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntPK, IdMixin, TenantBase, utcnow


class Setting(TenantBase):
    """Key/value parish configuration (financial year, currency, approval & notification options …)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigIntPK)


class Sequence(TenantBase):
    """Business code generator rows (``FAMILY`` → FAM000123). Locked with SELECT … FOR UPDATE."""

    __tablename__ = "sequences"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    padding: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    # Placeholders: {prefix} {year} {number}. Yearly sequences restart at 1 every calendar year.
    format: Mapped[str] = mapped_column(
        String(50), nullable=False, default="{prefix}{number}", server_default="{prefix}{number}"
    )
    yearly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())


class AuditLog(IdMixin, TenantBase):
    """Append-only audit trail. Never updated or deleted by the application."""

    __tablename__ = "audit_logs"

    occurred_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(BigIntPK, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    remarks: Mapped[str | None] = mapped_column(Text)

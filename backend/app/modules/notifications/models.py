"""Notification tables: in-app notifications, per-user preferences, template overrides, outbound queue."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, TenantBase, utcnow


class Notification(IdMixin, PublicIdMixin, TenantBase):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "is_read", "created_at"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_code: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(500))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    is_important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime())
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class NotificationPreference(IdMixin, TenantBase):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "event_code", "channel"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_code: Mapped[str] = mapped_column(String(60), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class NotificationTemplate(IdMixin, TenantBase):
    """Parish override of a default template (defaults live in code: ``notifications/catalog.py``)."""

    __tablename__ = "notification_templates"
    __table_args__ = (UniqueConstraint("event_code", "channel", "language"),)

    event_code: Mapped[str] = mapped_column(String(60), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigIntPK)


class OutboundMessage(IdMixin, PublicIdMixin, TenantBase):
    """Email/SMS/WhatsApp delivery queue with status tracking and retries."""

    __tablename__ = "outbound_messages"

    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigIntPK, index=True)
    event_code: Mapped[str | None] = mapped_column(String(60))
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime())

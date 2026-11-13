"""Weekly notices, announcements and parish news."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntPK, StandardMixin, TenantBase

CATEGORIES = ("WEEKLY", "ANNOUNCEMENT", "EVENT", "EMERGENCY", "DIOCESE", "NEWS")


class Notice(StandardMixin, TenantBase):
    __tablename__ = "notices"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    # Organisation that prepared it (None = parish office); decides who may edit it.
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    category: Mapped[str] = mapped_column(String(15), nullable=False, default="ANNOUNCEMENT", index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    title_local: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_local: Mapped[str | None] = mapped_column(Text)
    # {"all": true} or {"org_units": [internal ids]}
    audience: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=lambda: {"all": True})
    is_important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # member/public portal
    # Parish wall-clock times.
    publish_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(), index=True)
    # DRAFT, IN_REVIEW, REWORK, APPROVED (scheduled), PUBLISHED, REJECTED, ARCHIVED
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="DRAFT", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime())
    published_at: Mapped[datetime | None] = mapped_column(DateTime())  # when readers were notified
    archived_at: Mapped[datetime | None] = mapped_column(DateTime())
    archived_by: Mapped[int | None] = mapped_column(BigIntPK)

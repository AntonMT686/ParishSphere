"""Roles, permissions and scoped role assignments."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow

role_permissions = Table(
    "role_permissions",
    TenantBase.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(IdMixin, TenantBase):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class Role(StandardMixin, TenantBase):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # PARISH (parish-wide only), ORG_UNIT (must be scoped to an organisation unit) or ANY.
    scope_type: Mapped[str] = mapped_column(String(10), nullable=False, default="PARISH")

    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class UserRoleAssignment(IdMixin, PublicIdMixin, TenantBase):
    """A role held by a user, parish-wide (``org_unit_id`` NULL) or for one organisation unit.

    Assignments are never deleted: ending one sets ``ended_at`` so history ("who was secretary in
    2024?") remains answerable.
    """

    __tablename__ = "user_role_assignments"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    assigned_by: Mapped[int | None] = mapped_column(BigIntPK)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(), index=True)
    ended_by: Mapped[int | None] = mapped_column(BigIntPK)
    remarks: Mapped[str | None] = mapped_column(String(255))

    role: Mapped[Role] = relationship(lazy="joined")

    def is_active_on(self, day: date) -> bool:
        return (
            self.ended_at is None
            and self.valid_from <= day
            and (self.valid_to is None or self.valid_to >= day)
        )

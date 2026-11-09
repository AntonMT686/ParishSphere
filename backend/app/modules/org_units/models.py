"""Configurable parish organisation: types, positions, units (tree) and office bearers.

Parish Council, Committees, Anbiyam, Sabai, Societies and Associations are all *data*: rows in
``org_unit_types`` and ``org_units``. Nothing in the code hard-codes how many exist.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow


class OrgUnitType(StandardMixin, TenantBase):
    __tablename__ = "org_unit_types"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_plural: Mapped[str] = mapped_column(String(100), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # MEMBER: individuals join · FAMILY: whole families join (Anbiyam).
    member_kind: Mapped[str] = mapped_column(String(10), nullable=False, default="MEMBER")
    # e.g. {"min_age": 15, "max_age": 35, "genders": ["F"], "max_units_per_member": 1}
    # – enforced when members join (T8).
    membership_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    allow_multiple_units: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    code_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    positions: Mapped[list[OrgUnitPosition]] = relationship(
        order_by="OrgUnitPosition.sort_order",
        lazy="selectin",
        primaryjoin="and_(OrgUnitPosition.type_id == OrgUnitType.id, OrgUnitPosition.is_deleted.is_(False))",
        viewonly=True,
    )


class OrgUnitPosition(StandardMixin, TenantBase):
    """An office within a type (President, Secretary …). Holding it grants ``role`` automatically."""

    __tablename__ = "org_unit_positions"
    __table_args__ = (UniqueConstraint("type_id", "code"),)

    type_id: Mapped[int] = mapped_column(ForeignKey("org_unit_types.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(100))
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    max_holders: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    type: Mapped[OrgUnitType] = relationship(foreign_keys=[type_id])


class OrgUnit(StandardMixin, TenantBase):
    __tablename__ = "org_units"

    type_id: Mapped[int] = mapped_column(ForeignKey("org_unit_types.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    established_on: Mapped[date | None] = mapped_column(Date)
    meeting_place: Mapped[str | None] = mapped_column(String(255))
    meeting_schedule: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    contact_email: Mapped[str | None] = mapped_column(String(255))

    type: Mapped[OrgUnitType] = relationship(lazy="joined")
    parent: Mapped[OrgUnit | None] = relationship(remote_side="OrgUnit.id", lazy="joined", join_depth=1)


class OrgUnitOfficeBearer(IdMixin, PublicIdMixin, TenantBase):
    """Who held which position, when. Never deleted – ended terms remain as history."""

    __tablename__ = "org_unit_office_bearers"

    org_unit_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"), nullable=False, index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("org_unit_positions.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), index=True)
    holder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(), index=True)
    ended_by: Mapped[int | None] = mapped_column(BigIntPK)
    role_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("user_role_assignments.id"))
    remarks: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(BigIntPK)

    position: Mapped[OrgUnitPosition] = relationship(lazy="joined")

    def is_current(self, day: date) -> bool:
        return (
            self.ended_at is None
            and self.valid_from <= day
            and (self.valid_to is None or self.valid_to >= day)
        )

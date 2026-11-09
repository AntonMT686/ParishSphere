"""Parish register: families, members, their histories, and organisation memberships."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow


class FamilyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING_ANBIYAM = "PENDING_ANBIYAM"
    INACTIVE = "INACTIVE"
    TRANSFERRED_OUT = "TRANSFERRED_OUT"
    MERGED = "MERGED"


class MemberStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DECEASED = "DECEASED"
    TRANSFERRED_OUT = "TRANSFERRED_OUT"


RELATIONSHIPS = (
    "HEAD",
    "SPOUSE",
    "SON",
    "DAUGHTER",
    "FATHER",
    "MOTHER",
    "BROTHER",
    "SISTER",
    "GRANDSON",
    "GRANDDAUGHTER",
    "SON_IN_LAW",
    "DAUGHTER_IN_LAW",
    "FATHER_IN_LAW",
    "MOTHER_IN_LAW",
    "GRANDFATHER",
    "GRANDMOTHER",
    "NEPHEW",
    "NIECE",
    "OTHER_RELATIVE",
    "OTHER",
)
GENDERS = ("M", "F", "O")
MARITAL_STATUSES = ("SINGLE", "MARRIED", "WIDOWED", "SEPARATED", "RELIGIOUS")


class Family(StandardMixin, TenantBase):
    __tablename__ = "families"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    family_name: Mapped[str] = mapped_column(String(200), nullable=False)
    family_name_local: Mapped[str | None] = mapped_column(String(200))
    search_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    head_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", use_alter=True, name="fk_families_head_member_id_members")
    )
    anbiyam_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(30))
    phone_digits: Mapped[str | None] = mapped_column(String(15), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    registered_on: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=FamilyStatus.ACTIVE, index=True)
    previous_parish: Mapped[str | None] = mapped_column(String(200))
    previous_diocese: Mapped[str | None] = mapped_column(String(200))
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"))
    remarks: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list[Member]] = relationship(
        back_populates="family",
        foreign_keys="Member.family_id",
        primaryjoin="and_(Member.family_id == Family.id, Member.is_deleted.is_(False))",
        order_by="Member.id",
        viewonly=True,
    )


class Member(StandardMixin, TenantBase):
    __tablename__ = "members"
    __table_args__ = (Index("ix_members_search_name_dob", "search_name", "date_of_birth"),)

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100))
    name_local: Mapped[str | None] = mapped_column(String(200))
    search_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gender: Mapped[str] = mapped_column(String(1), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    relationship_to_head: Mapped[str] = mapped_column(String(20), nullable=False, default="OTHER")
    phone: Mapped[str | None] = mapped_column(String(30))
    phone_digits: Mapped[str | None] = mapped_column(String(15), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    education: Mapped[str | None] = mapped_column(String(200))
    occupation: Mapped[str | None] = mapped_column(String(200))
    marital_status: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=MemberStatus.ACTIVE, index=True)
    date_of_death: Mapped[date | None] = mapped_column(Date)
    # Sacramental summary (full registers are configurable – T21).
    baptism_date: Mapped[date | None] = mapped_column(Date)
    baptism_place: Mapped[str | None] = mapped_column(String(200))
    baptism_register_ref: Mapped[str | None] = mapped_column(String(50))
    communion_date: Mapped[date | None] = mapped_column(Date)
    communion_place: Mapped[str | None] = mapped_column(String(200))
    confirmation_date: Mapped[date | None] = mapped_column(Date)
    confirmation_place: Mapped[str | None] = mapped_column(String(200))
    marriage_date: Mapped[date | None] = mapped_column(Date)
    marriage_place: Mapped[str | None] = mapped_column(String(200))
    marriage_register_ref: Mapped[str | None] = mapped_column(String(50))
    remarks: Mapped[str | None] = mapped_column(Text)

    family: Mapped[Family] = relationship(foreign_keys=[family_id], back_populates="members", lazy="joined")

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p)


class FamilyAnbiyamHistory(IdMixin, TenantBase):
    __tablename__ = "family_anbiyam_history"

    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), nullable=False, index=True)
    anbiyam_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"), nullable=False, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(255))
    changed_by: Mapped[int | None] = mapped_column(BigIntPK)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class MemberFamilyHistory(IdMixin, TenantBase):
    __tablename__ = "member_family_history"

    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False, index=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), nullable=False, index=True)
    relationship_to_head: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)  # REGISTERED, ADDED, MOVED, SPLIT, MERGE
    changed_by: Mapped[int | None] = mapped_column(BigIntPK)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class FamilyEvent(IdMixin, TenantBase):
    """Timeline of significant family events (registration, transfers, merges, splits, deaths …)."""

    __tablename__ = "family_events"

    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    related_family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"))
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    performed_by: Mapped[int | None] = mapped_column(BigIntPK)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, index=True)


class OrgUnitMembership(IdMixin, PublicIdMixin, TenantBase):
    """A member (or, for family-based types, a family) belonging to an organisation. Ended, never deleted."""

    __tablename__ = "org_unit_memberships"
    __table_args__ = (
        CheckConstraint(
            "(member_id IS NOT NULL AND family_id IS NULL) OR (member_id IS NULL AND family_id IS NOT NULL)",
            name="one_subject",
        ),
    )

    org_unit_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"), nullable=False, index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), index=True)
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"), index=True)
    joined_on: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    left_on: Mapped[date | None] = mapped_column(Date)
    end_reason: Mapped[str | None] = mapped_column(String(100))
    remarks: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int | None] = mapped_column(BigIntPK)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

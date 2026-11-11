"""Parish profile (single row) and priests with assignment history."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow


class ParishProfile(TenantBase):
    """The parish's own description and regional settings. Exactly one row (id = 1).

    Fields needed before sign-in (name, logo, colour, language, currency, financial year) are copied
    to the master database's ``tenant_settings`` on every change, so the login page can be branded.
    """

    __tablename__ = "parish_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(200))
    patron_saint: Mapped[str | None] = mapped_column(String(200))
    established_on: Mapped[date | None] = mapped_column(Date)
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    about: Mapped[str | None] = mapped_column(Text)
    logo_key: Mapped[str | None] = mapped_column(String(255))
    logo_content_type: Mapped[str | None] = mapped_column(String(50))
    logo_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    primary_color: Mapped[str | None] = mapped_column(String(9))
    default_language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    fy_start_month: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=4)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigIntPK)


class Priest(StandardMixin, TenantBase):
    __tablename__ = "priests"

    title: Mapped[str] = mapped_column(String(50), nullable=False, default="Rev. Fr.")
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(200))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    ordination_date: Mapped[date | None] = mapped_column(Date)
    # DIOCESAN or RELIGIOUS (member of a congregation/order).
    clergy_type: Mapped[str] = mapped_column(String(10), nullable=False, default="DIOCESAN")
    home_diocese: Mapped[str | None] = mapped_column(String(200))
    congregation: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    # ACTIVE, RETIRED, DECEASED, LEFT
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    remarks: Mapped[str | None] = mapped_column(Text)

    assignments: Mapped[list[PriestAssignment]] = relationship(
        back_populates="priest", order_by="PriestAssignment.appointed_on.desc()", lazy="selectin"
    )

    @property
    def display_name(self) -> str:
        return f"{self.title} {self.full_name}".strip()


class PriestAssignment(IdMixin, PublicIdMixin, TenantBase):
    """A priest's service in this parish, from ``appointed_on`` until the handover date ``relieved_on``
    (exclusive). Ended, never deleted."""

    __tablename__ = "priest_assignments"

    priest_id: Mapped[int] = mapped_column(ForeignKey("priests.id"), nullable=False, index=True)
    # PARISH_PRIEST, ASSISTANT_PRIEST, RESIDENT_PRIEST, DEACON, OTHER
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    appointed_on: Mapped[date] = mapped_column(Date, nullable=False)
    relieved_on: Mapped[date | None] = mapped_column(Date, index=True)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    appointment_ref: Mapped[str | None] = mapped_column(String(100))
    relieving_reason: Mapped[str | None] = mapped_column(String(255))
    remarks: Mapped[str | None] = mapped_column(String(255))
    role_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("user_role_assignments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(BigIntPK)

    priest: Mapped[Priest] = relationship(back_populates="assignments")

    def is_current(self, on: date) -> bool:
        # relieved_on is the handover date (exclusive).
        return self.appointed_on <= on and (self.relieved_on is None or self.relieved_on > on)

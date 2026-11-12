"""Activities, meetings (agenda, attendance, minutes) and action items – common to every organisation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow

# Records that only change through the approval workflow while it runs.
EDITABLE = ("DRAFT", "REWORK")


class Activity(StandardMixin, TenantBase):
    __tablename__ = "activities"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)  # None = parish
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(255))
    responsible_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    responsible_name: Mapped[str | None] = mapped_column(String(200))
    planned_details: Mapped[str | None] = mapped_column(Text)
    actual_details: Mapped[str | None] = mapped_column(Text)
    planned_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    participant_count: Mapped[int | None] = mapped_column(Integer)
    # DRAFT, IN_REVIEW, REWORK, APPROVED, REJECTED, COMPLETED, CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime())

    participants: Mapped[list[ActivityParticipant]] = relationship(
        back_populates="activity",
        order_by="ActivityParticipant.id",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class ActivityParticipant(IdMixin, TenantBase):
    __tablename__ = "activity_participants"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False, index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100))

    activity: Mapped[Activity] = relationship(back_populates="participants")


class Meeting(StandardMixin, TenantBase):
    __tablename__ = "meetings"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    meeting_type: Mapped[str] = mapped_column(String(20), nullable=False, default="REGULAR")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, index=True)  # local wall time
    ends_at: Mapped[datetime | None] = mapped_column(DateTime())
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    # SCHEDULED, HELD, CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCHEDULED", index=True)
    called_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime())

    agenda: Mapped[list[AgendaItem]] = relationship(
        order_by="AgendaItem.seq", lazy="selectin", cascade="all, delete-orphan"
    )
    attendance: Mapped[list[Attendance]] = relationship(
        order_by="Attendance.id", lazy="selectin", cascade="all, delete-orphan"
    )
    minutes: Mapped[MeetingMinutes | None] = relationship(
        back_populates="meeting", lazy="selectin", uselist=False
    )


class AgendaItem(IdMixin, TenantBase):
    __tablename__ = "meeting_agenda_items"

    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    presenter: Mapped[str | None] = mapped_column(String(200))


class Attendance(IdMixin, TenantBase):
    """One row per invitee: a member, or a family for family-based organisations (Anbiyam), or a guest."""

    __tablename__ = "meeting_attendance"

    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # PRESENT, ABSENT, EXCUSED
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PRESENT")
    remarks: Mapped[str | None] = mapped_column(String(255))


class MeetingMinutes(StandardMixin, TenantBase):
    __tablename__ = "meeting_minutes"

    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), unique=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # DRAFT, IN_REVIEW, REWORK, APPROVED, REJECTED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime())

    meeting: Mapped[Meeting] = relationship(back_populates="minutes")
    points: Mapped[list[DiscussionPoint]] = relationship(
        order_by="DiscussionPoint.seq", lazy="selectin", cascade="all, delete-orphan"
    )
    resolutions: Mapped[list[Resolution]] = relationship(
        order_by="Resolution.seq", lazy="selectin", cascade="all, delete-orphan"
    )


class DiscussionPoint(IdMixin, TenantBase):
    __tablename__ = "discussion_points"

    minutes_id: Mapped[int] = mapped_column(ForeignKey("meeting_minutes.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    discussion: Mapped[str | None] = mapped_column(Text)


class Resolution(IdMixin, TenantBase):
    __tablename__ = "resolutions"

    minutes_id: Mapped[int] = mapped_column(ForeignKey("meeting_minutes.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # PASSED, DEFERRED, REJECTED
    decision: Mapped[str] = mapped_column(String(10), nullable=False, default="PASSED")


class ActionItem(StandardMixin, TenantBase):
    """A responsibility with a due date – from a meeting decision, an activity, or recorded directly."""

    __tablename__ = "action_items"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="MANUAL"
    )  # MEETING, ACTIVITY
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id"), index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"), index=True)
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    owner_name: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    # OPEN, IN_PROGRESS, DONE, CANCELLED (overdue is derived from due_date)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="OPEN", index=True)
    progress_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    completed_on: Mapped[date | None] = mapped_column(Date)
    last_reminded_on: Mapped[date | None] = mapped_column(Date)

    updates: Mapped[list[ActionItemUpdate]] = relationship(
        order_by="ActionItemUpdate.id", lazy="selectin", cascade="all, delete-orphan"
    )


class ActionItemUpdate(IdMixin, PublicIdMixin, TenantBase):
    __tablename__ = "action_item_updates"

    action_item_id: Mapped[int] = mapped_column(ForeignKey("action_items.id"), nullable=False, index=True)
    text: Mapped[str | None] = mapped_column(Text)
    progress_pct: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str | None] = mapped_column(String(15))
    created_by: Mapped[int | None] = mapped_column(BigIntPK)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

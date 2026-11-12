from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.attachments.service import AttachmentOut


class UnitRef(BaseModel):
    id: str
    name: str
    type_code: str


class PersonRef(BaseModel):
    id: str
    name: str


class Actions(BaseModel):
    """What the current user may do with the record (UI hints; the API enforces)."""

    edit: bool = False
    submit: bool = False
    delete: bool = False
    complete: bool = False
    cancel: bool = False
    attach: bool = False


# ============================================================================ activities
class ParticipantIn(BaseModel):
    member_id: str | None = Field(default=None, max_length=26)
    name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _who(self) -> ParticipantIn:
        if not self.member_id and not (self.name and self.name.strip()):
            raise ValueError("Choose a member or type a name")
        return self


class ParticipantOut(BaseModel):
    member_id: str | None
    name: str
    role: str | None


class ActivityIn(BaseModel):
    org_unit_id: str | None = Field(
        default=None, max_length=26, description="Omit for a parish-level activity"
    )
    title: str = Field(min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=30)
    description: str | None = Field(default=None, max_length=5000)
    activity_date: date
    end_date: date | None = None
    location: str | None = Field(default=None, max_length=255)
    responsible_member_id: str | None = Field(default=None, max_length=26)
    responsible_name: str | None = Field(default=None, max_length=200)
    planned_details: str | None = Field(default=None, max_length=10000)
    actual_details: str | None = Field(default=None, max_length=10000)
    planned_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    actual_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    participant_count: int | None = Field(default=None, ge=0, le=100000)
    remarks: str | None = Field(default=None, max_length=5000)
    participants: list[ParticipantIn] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def _dates(self) -> ActivityIn:
        if self.end_date and self.end_date < self.activity_date:
            raise ValueError("The end date is before the start date")
        return self


class ActivityUpdate(ActivityIn):
    org_unit_id: str | None = Field(default=None, max_length=26)


class CompleteIn(BaseModel):
    actual_details: str = Field(min_length=2, max_length=10000)
    actual_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    participant_count: int | None = Field(default=None, ge=0, le=100000)
    participants: list[ParticipantIn] | None = Field(default=None, max_length=500)


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class SubmitIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class ActivityListOut(BaseModel):
    id: str
    code: str
    title: str
    category: str | None
    org_unit: UnitRef | None
    activity_date: date
    end_date: date | None
    location: str | None
    responsible: str | None
    status: str
    planned_amount: Decimal | None
    actual_amount: Decimal | None
    participant_count: int | None


class ActivityOut(ActivityListOut):
    description: str | None
    responsible_member: PersonRef | None
    planned_details: str | None
    actual_details: str | None
    remarks: str | None
    participants: list[ParticipantOut]
    created_by: str | None
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    completed_at: datetime | None
    approval_id: str | None
    can: Actions


# ============================================================================ meetings
class AgendaIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    presenter: str | None = Field(default=None, max_length=200)


class MeetingIn(BaseModel):
    org_unit_id: str | None = Field(default=None, max_length=26)
    title: str = Field(min_length=2, max_length=200)
    meeting_type: Literal["REGULAR", "SPECIAL", "GENERAL_BODY", "EMERGENCY"] = "REGULAR"
    scheduled_at: datetime = Field(description="Local date and time of the parish")
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    agenda: list[AgendaIn] = Field(default_factory=list, max_length=50)
    notify: bool = True

    @model_validator(mode="after")
    def _times(self) -> MeetingIn:
        self.scheduled_at = self.scheduled_at.replace(tzinfo=None, second=0, microsecond=0)
        if self.ends_at:
            self.ends_at = self.ends_at.replace(tzinfo=None, second=0, microsecond=0)
            if self.ends_at <= self.scheduled_at:
                raise ValueError("The meeting must end after it starts")
        return self


class MeetingListOut(BaseModel):
    id: str
    code: str
    title: str
    meeting_type: str
    org_unit: UnitRef | None
    scheduled_at: datetime
    ends_at: datetime | None
    location: str | None
    status: str
    minutes_status: str | None
    open_actions: int


class AgendaOut(AgendaIn):
    seq: int


class AttendanceRow(BaseModel):
    member_id: str | None = Field(default=None, max_length=26)
    family_id: str | None = Field(default=None, max_length=26)
    name: str = Field(min_length=1, max_length=200)
    status: Literal["PRESENT", "ABSENT", "EXCUSED"] = "PRESENT"
    remarks: str | None = Field(default=None, max_length=255)


class AttendanceOut(BaseModel):
    recorded: bool
    rows: list[AttendanceRow]
    present: int
    total: int


class AttendanceIn(BaseModel):
    rows: list[AttendanceRow] = Field(max_length=1000)


class PointIn(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    discussion: str | None = Field(default=None, max_length=10000)


class ResolutionIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    decision: Literal["PASSED", "DEFERRED", "REJECTED"] = "PASSED"


class MinutesIn(BaseModel):
    summary: str | None = Field(default=None, max_length=20000)
    points: list[PointIn] = Field(default_factory=list, max_length=100)
    resolutions: list[ResolutionIn] = Field(default_factory=list, max_length=100)


class MinutesOut(BaseModel):
    id: str
    status: str
    summary: str | None
    points: list[PointIn]
    resolutions: list[ResolutionIn]
    recorded_by: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    approval_id: str | None
    can_edit: bool
    can_submit: bool


class MeetingOut(MeetingListOut):
    description: str | None
    agenda: list[AgendaOut]
    called_by: str | None
    cancel_reason: str | None
    minutes: MinutesOut | None
    can: Actions


# ============================================================================ action items
class ActionIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    org_unit_id: str | None = Field(default=None, max_length=26)
    meeting_id: str | None = Field(default=None, max_length=26)
    activity_id: str | None = Field(default=None, max_length=26)
    owner_user_id: str | None = Field(default=None, max_length=26)
    owner_name: str | None = Field(default=None, max_length=200)
    due_date: date | None = None


class ActionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    owner_user_id: str | None = Field(default=None, max_length=26)
    owner_name: str | None = Field(default=None, max_length=200)
    due_date: date | None = None


class ProgressIn(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"] | None = None


class ProgressOut(BaseModel):
    id: str
    text: str | None
    progress_pct: int | None
    status: str | None
    by: str | None
    at: datetime


class SourceRef(BaseModel):
    type: str
    id: str | None
    title: str | None


class ActionItemOut(BaseModel):
    id: str
    code: str
    title: str
    description: str | None
    org_unit: UnitRef | None
    source: SourceRef
    owner: PersonRef | None
    owner_name: str | None
    due_date: date | None
    status: str
    overdue: bool
    progress_pct: int
    completed_on: date | None
    created_at: datetime
    updates: list[ProgressOut]
    can_update: bool
    can_edit: bool


# ============================================================================ calendar
class CalendarEvent(BaseModel):
    id: str
    kind: Literal["ACTIVITY", "MEETING"]
    title: str
    start: datetime
    end: datetime | None
    all_day: bool
    status: str
    org_unit: UnitRef | None
    location: str | None
    link: str


__all__ = ["AttachmentOut"]

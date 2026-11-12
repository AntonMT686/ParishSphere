"""Business rules for activities, meetings, minutes and action items, and their workflow handlers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.sequences import next_code
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.db.base import utcnow
from app.db.tenant import TenantDescriptor
from app.modules.activities.models import (
    EDITABLE,
    ActionItem,
    ActionItemUpdate,
    Activity,
    Attendance,
    Meeting,
    MeetingMinutes,
)
from app.modules.identity.models import User
from app.modules.notifications.service import emit
from app.modules.org_units.models import OrgUnit, OrgUnitOfficeBearer
from app.modules.org_units.service import current_bearers_stmt
from app.modules.people.models import Family, Member, OrgUnitMembership
from app.modules.rbac.service import PermissionScope
from app.modules.workflow import service as wf
from app.modules.workflow.models import WorkflowInstance
from app.modules.workflow.registry import WorkflowHandler, register_handler

ACTIVITY_CATEGORIES = (
    "SPIRITUAL",
    "LITURGICAL",
    "CHARITY",
    "SOCIAL",
    "CULTURAL",
    "EDUCATIONAL",
    "YOUTH",
    "FAMILY",
    "OTHER",
)
OPEN_ACTION = ("OPEN", "IN_PROGRESS")


# ============================================================================ helpers
def require_scope(scope: PermissionScope, org_unit_id: int | None) -> None:
    if not scope.allows(org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": scope.code}])


def parish_now(db: Session) -> datetime:
    """Current wall-clock time in the parish's time zone (meetings are stored as local times)."""
    from app.modules.parish.models import ParishProfile

    p = db.get(ParishProfile, 1)
    tz = ZoneInfo(p.timezone if p and p.timezone else "Asia/Kolkata")
    return datetime.now(tz).replace(tzinfo=None, microsecond=0)


def unit_name(db: Session, org_unit_id: int | None) -> str:
    unit = db.get(OrgUnit, org_unit_id) if org_unit_id else None
    return unit.name if unit else "Parish"


def office_bearer_users(db: Session, org_unit_id: int | None) -> set[int]:
    if org_unit_id is None:
        return set()
    return {
        b.user_id
        for b in db.scalars(current_bearers_stmt(org_unit_id))
        if isinstance(b, OrgUnitOfficeBearer) and b.user_id
    }


def fmt_when(dt: datetime) -> str:
    return dt.strftime("%d %b %Y, %I:%M %p").replace(" 0", " ")


# ============================================================================ activities
def get_activity(db: Session, public_id: str) -> Activity:
    a = db.scalar(select(Activity).where(Activity.public_id == public_id, Activity.is_deleted.is_(False)))
    if a is None:
        raise NotFound("Activity not found")
    return a


def ensure_editable(status: str, what: str = "record") -> None:
    if status not in EDITABLE:
        raise Conflict(
            f"This {what} can only be changed while it is a draft or returned for rework", code="NOT_EDITABLE"
        )


def new_activity(db: Session, data: dict[str, Any], actor_id: int) -> Activity:
    a = Activity(
        code=next_code(db, "ACTIVITY", data.get("activity_date")), status="DRAFT", created_by=actor_id, **data
    )
    db.add(a)
    db.flush()
    return a


def submit_activity(
    db: Session, tenant: TenantDescriptor, a: Activity, actor_id: int, comment: str | None = None
) -> WorkflowInstance:
    if a.status == "REWORK":
        inst = wf.active_instance(db, "ACTIVITY", a.public_id)
        if inst is None:
            raise Conflict("No approval is waiting for this activity", code="INVALID_STATE")
        return wf.resubmit(
            db, tenant, inst, actor_id, comment, title=f"{a.code} · {a.title}", context=_activity_ctx(a)
        )
    if a.status != "DRAFT":
        raise Conflict("Only draft activities can be submitted", code="INVALID_STATE")
    return wf.submit(
        db,
        tenant,
        entity_type="ACTIVITY",
        entity_id=a.public_id,
        title=f"{a.code} · {a.title}",
        actor_id=actor_id,
        org_unit_id=a.org_unit_id,
        context=_activity_ctx(a),
        link=f"/activities/{a.public_id}",
        comment=comment,
    )


def _activity_ctx(a: Activity) -> dict[str, Any]:
    amount = a.actual_amount if a.actual_amount is not None else a.planned_amount
    return {"category": a.category, "amount": float(amount) if amount is not None else None}


def _activity_for(db: Session, inst: WorkflowInstance) -> Activity:
    return get_activity(db, inst.entity_id)


def _set_activity(status: str):  # type: ignore[no-untyped-def]
    def cb(db: Session, inst: WorkflowInstance) -> None:
        a = _activity_for(db, inst)
        a.status = status
        if status == "IN_REVIEW":
            a.submitted_at = utcnow()
        elif status == "APPROVED":
            a.approved_at = utcnow()

    return cb


register_handler(
    "ACTIVITY",
    WorkflowHandler(
        on_submitted=_set_activity("IN_REVIEW"),
        on_approved=_set_activity("APPROVED"),
        on_rejected=_set_activity("REJECTED"),
        on_rework=_set_activity("REWORK"),
        on_withdrawn=_set_activity("DRAFT"),
    ),
)


# ============================================================================ meetings
def get_meeting(db: Session, public_id: str) -> Meeting:
    m = db.scalar(select(Meeting).where(Meeting.public_id == public_id, Meeting.is_deleted.is_(False)))
    if m is None:
        raise NotFound("Meeting not found")
    return m


def meeting_recipients(db: Session, m: Meeting) -> set[int]:
    return office_bearer_users(db, m.org_unit_id) | ({m.called_by} if m.called_by else set())


def notify_meeting(
    db: Session, tenant: TenantDescriptor, m: Meeting, event: str, actor_id: int | None, **extra: Any
) -> None:
    emit(
        db,
        tenant,
        event,
        meeting_recipients(db, m),
        {"title": m.title, "when": fmt_when(m.scheduled_at), "place": m.location or "", **extra},
        link=f"/meetings/{m.public_id}",
        entity_type="MEETING",
        entity_id=m.public_id,
        exclude_user_id=actor_id,
    )


def minutes_locked(m: Meeting) -> bool:
    return m.minutes is not None and m.minutes.status not in EDITABLE


def invitees(db: Session, m: Meeting) -> list[dict[str, Any]]:
    """Current members of the organisation – families for Anbiyam and other family-based types."""
    if m.org_unit_id is None:
        return []
    unit = db.get(OrgUnit, m.org_unit_id)
    out: list[dict[str, Any]] = []

    def add_family(fam: Family | None) -> None:
        if fam and not fam.is_deleted and fam.status not in ("MERGED", "TRANSFERRED_OUT", "INACTIVE"):
            out.append({"member_id": None, "family_id": fam.id, "name": f"{fam.family_name} ({fam.code})"})

    if unit is not None and unit.type.code == "ANBIYAM":
        for fam in db.scalars(select(Family).where(Family.anbiyam_id == unit.id)):
            add_family(fam)
    else:
        day = m.scheduled_at.date()
        rows = db.scalars(
            select(OrgUnitMembership).where(
                OrgUnitMembership.org_unit_id == m.org_unit_id,
                OrgUnitMembership.joined_on <= day,
                (OrgUnitMembership.left_on.is_(None)) | (OrgUnitMembership.left_on > day),
            )
        ).all()
        for r in rows:
            if r.member_id:
                mem = db.get(Member, r.member_id)
                if mem and mem.status == "ACTIVE" and not mem.is_deleted:
                    out.append({"member_id": mem.id, "family_id": None, "name": mem.full_name})
            elif r.family_id:
                add_family(db.get(Family, r.family_id))
    return sorted(out, key=lambda x: x["name"].lower())


def save_attendance(db: Session, m: Meeting, rows: list[dict[str, Any]]) -> None:
    if m.status == "CANCELLED":
        raise Conflict("The meeting was cancelled", code="INVALID_STATE")
    if minutes_locked(m):
        raise Conflict("Attendance is locked once the minutes are submitted", code="NOT_EDITABLE")
    m.attendance.clear()
    db.flush()
    for r in rows:
        m.attendance.append(Attendance(**r))
    if m.scheduled_at <= parish_now(db) and m.status == "SCHEDULED":
        m.status = "HELD"


def get_minutes(db: Session, public_id: str) -> MeetingMinutes:
    mm = db.scalar(select(MeetingMinutes).where(MeetingMinutes.public_id == public_id))
    if mm is None:
        raise NotFound("Minutes not found")
    return mm


def submit_minutes(
    db: Session, tenant: TenantDescriptor, mm: MeetingMinutes, actor_id: int, comment: str | None = None
) -> WorkflowInstance:
    m = mm.meeting
    if not (mm.summary or mm.points or mm.resolutions):
        raise ValidationFailed("Write the minutes before submitting them", code="MINUTES_EMPTY")
    title = f"Minutes · {m.title} ({m.scheduled_at:%d %b %Y})"
    if mm.status == "REWORK":
        inst = wf.active_instance(db, "MEETING_MINUTES", mm.public_id)
        if inst is None:
            raise Conflict("No approval is waiting for these minutes", code="INVALID_STATE")
        return wf.resubmit(db, tenant, inst, actor_id, comment, title=title)
    if mm.status != "DRAFT":
        raise Conflict("Only draft minutes can be submitted", code="INVALID_STATE")
    return wf.submit(
        db,
        tenant,
        entity_type="MEETING_MINUTES",
        entity_id=mm.public_id,
        title=title,
        actor_id=actor_id,
        org_unit_id=m.org_unit_id,
        link=f"/meetings/{m.public_id}",
        comment=comment,
    )


def _set_minutes(status: str):  # type: ignore[no-untyped-def]
    def cb(db: Session, inst: WorkflowInstance) -> None:
        mm = get_minutes(db, inst.entity_id)
        mm.status = status
        if status == "IN_REVIEW":
            mm.submitted_at = utcnow()
        elif status == "APPROVED":
            mm.approved_at = utcnow()

    return cb


register_handler(
    "MEETING_MINUTES",
    WorkflowHandler(
        on_submitted=_set_minutes("IN_REVIEW"),
        on_approved=_set_minutes("APPROVED"),
        on_rejected=_set_minutes("REJECTED"),
        on_rework=_set_minutes("REWORK"),
        on_withdrawn=_set_minutes("DRAFT"),
    ),
)


# ============================================================================ action items
def get_action(db: Session, public_id: str) -> ActionItem:
    a = db.scalar(
        select(ActionItem).where(ActionItem.public_id == public_id, ActionItem.is_deleted.is_(False))
    )
    if a is None:
        raise NotFound("Action item not found")
    return a


def action_source(db: Session, a: ActionItem) -> str:
    if a.meeting_id:
        m = db.get(Meeting, a.meeting_id)
        return f"Meeting: {m.title}" if m else ""
    if a.activity_id:
        act = db.get(Activity, a.activity_id)
        return f"Activity: {act.title}" if act else ""
    return ""


def notify_assigned(db: Session, tenant: TenantDescriptor, a: ActionItem, actor_id: int) -> None:
    if a.owner_user_id:
        emit(
            db,
            tenant,
            "action_item.assigned",
            [a.owner_user_id],
            {
                "title": a.title,
                "due_date": a.due_date.strftime("%d %b %Y") if a.due_date else "",
                "source": action_source(db, a),
            },
            link=f"/action-items?open={a.public_id}",
            entity_type="ACTION_ITEM",
            entity_id=a.public_id,
            exclude_user_id=actor_id,
        )


def new_action(db: Session, tenant: TenantDescriptor, data: dict[str, Any], actor_id: int) -> ActionItem:
    if data.get("owner_user_id") and not data.get("owner_name"):
        u = db.get(User, data["owner_user_id"])
        data["owner_name"] = u.full_name if u else None
    a = ActionItem(
        code=next_code(db, "ACTION_ITEM"), status="OPEN", progress_pct=0, created_by=actor_id, **data
    )
    db.add(a)
    db.flush()
    notify_assigned(db, tenant, a, actor_id)
    return a


def add_progress(
    db: Session, a: ActionItem, actor_id: int, *, text: str | None, progress: int | None, status: str | None
) -> ActionItemUpdate:
    if a.status in ("DONE", "CANCELLED") and status in (None, a.status):
        raise Conflict("This action item is closed", code="INVALID_STATE")
    if not (text or progress is not None or status):
        raise ValidationFailed("Nothing to update")
    if progress is not None:
        a.progress_pct = progress
        if status is None and a.status == "OPEN" and progress > 0:
            status = "IN_PROGRESS"
    if status:
        a.status = status
        if status == "DONE":
            a.progress_pct, a.completed_on = 100, date.today()
        elif a.completed_on is not None:
            a.completed_on = None
    a.updated_by = actor_id
    u = ActionItemUpdate(
        action_item_id=a.id, text=text, progress_pct=progress, status=status, created_by=actor_id
    )
    a.updates.append(u)
    db.flush()
    return u


# ============================================================================ reminders
def run_reminders(db: Session, tenant: TenantDescriptor, now: datetime | None = None) -> dict[str, int]:
    """Meeting reminders (~24 h ahead, once) and action-item reminders (due tomorrow, due today,
    then weekly while overdue)."""
    now = now or parish_now(db)
    meetings = db.scalars(
        select(Meeting).where(
            Meeting.status == "SCHEDULED",
            Meeting.is_deleted.is_(False),
            Meeting.reminder_sent_at.is_(None),
            Meeting.scheduled_at > now,
            Meeting.scheduled_at <= now + timedelta(hours=24),
        )
    ).all()
    for m in meetings:
        notify_meeting(db, tenant, m, "meeting.reminder", None)
        m.reminder_sent_at = utcnow()
    today = now.date()
    sent = 0
    for a in db.scalars(
        select(ActionItem).where(
            ActionItem.status.in_(OPEN_ACTION),
            ActionItem.is_deleted.is_(False),
            ActionItem.owner_user_id.is_not(None),
            ActionItem.due_date.is_not(None),
            ActionItem.due_date <= today + timedelta(days=1),
        )
    ):
        assert a.due_date is not None
        days = (a.due_date - today).days
        due = days in (0, 1)
        overdue = days < 0 and (a.last_reminded_on is None or (today - a.last_reminded_on).days >= 7)
        if a.last_reminded_on == today or not (due or overdue):
            continue
        emit(
            db,
            tenant,
            "action_item.due",
            [a.owner_user_id],  # type: ignore[list-item]
            {"title": a.title, "due_date": a.due_date.strftime("%d %b %Y")},
            link=f"/action-items?open={a.public_id}",
            entity_type="ACTION_ITEM",
            entity_id=a.public_id,
        )
        a.last_reminded_on = today
        sent += 1
    db.flush()
    return {"meetings": len(meetings), "action_items": sent}

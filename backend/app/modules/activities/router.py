"""Activities (``/activities``), meetings & minutes (``/meetings``), action items (``/action-items``) and the
calendar (``/calendar``). Every query is limited to the organisations the user's roles cover."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import changes, record_audit
from app.common.exports import Column, ExportFormat, export_table, render_pdf
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.common.storage import content_disposition
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.db.base import utcnow
from app.modules.activities import service as svc
from app.modules.activities.models import (
    EDITABLE,
    ActionItem,
    Activity,
    ActivityParticipant,
    AgendaItem,
    Attendance,
    DiscussionPoint,
    Meeting,
    MeetingMinutes,
    Resolution,
)
from app.modules.activities.schemas import (
    ActionIn,
    ActionItemOut,
    Actions,
    ActionUpdate,
    ActivityIn,
    ActivityListOut,
    ActivityOut,
    ActivityUpdate,
    AgendaOut,
    AttendanceIn,
    AttendanceOut,
    AttendanceRow,
    CalendarEvent,
    CompleteIn,
    MeetingIn,
    MeetingListOut,
    MeetingOut,
    MinutesIn,
    MinutesOut,
    ParticipantIn,
    ParticipantOut,
    PersonRef,
    PointIn,
    ProgressIn,
    ProgressOut,
    ReasonIn,
    ResolutionIn,
    SourceRef,
    SubmitIn,
    UnitRef,
)
from app.modules.attachments.service import AttachmentOut, add_attachment, list_attachments, remove_attachment
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.org_units.models import OrgUnit
from app.modules.people.models import Family, Member
from app.modules.rbac.deps import require_perm
from app.modules.rbac.service import PermissionScope
from app.modules.workflow.models import WorkflowInstance
from app.tenancy.deps import TenantSession

activities_router = APIRouter(prefix="/activities", tags=["activities"])
meetings_router = APIRouter(prefix="/meetings", tags=["meetings"])
actions_router = APIRouter(prefix="/action-items", tags=["action items"])
calendar_router = APIRouter(prefix="/calendar", tags=["calendar"])


def _p(code: str):  # type: ignore[no-untyped-def]
    return Annotated[PermissionScope, Depends(require_perm(code))]


ActView, ActCreate, ActUpdate, ActDelete, ActSubmit, ActExport = (
    _p("activity.view"),
    _p("activity.create"),
    _p("activity.update"),
    _p("activity.delete"),
    _p("activity.submit"),
    _p("activity.export"),
)
MtgView, MtgCreate, MtgUpdate, MtgDelete, MtgSubmit, MtgExport = (
    _p("meeting.view"),
    _p("meeting.create"),
    _p("meeting.update"),
    _p("meeting.delete"),
    _p("meeting.submit"),
    _p("meeting.export"),
)


# ============================================================================ shared helpers
class Refs:
    """Per-request cache for organisation / user / member names."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.units: dict[int, UnitRef] = {}
        self.users: dict[int, User | None] = {}

    def unit(self, unit_id: int | None) -> UnitRef | None:
        if unit_id is None:
            return None
        if unit_id not in self.units:
            u = self.db.get(OrgUnit, unit_id)
            self.units[unit_id] = (
                UnitRef(id=u.public_id, name=u.name, type_code=u.type.code)
                if u
                else UnitRef(id="", name="—", type_code="")
            )
        return self.units[unit_id]

    def user(self, user_id: int | None) -> User | None:
        if user_id is None:
            return None
        if user_id not in self.users:
            self.users[user_id] = self.db.get(User, user_id)
        return self.users[user_id]

    def user_name(self, user_id: int | None) -> str | None:
        u = self.user(user_id)
        return u.full_name if u else None


def _unit_id(db: Session, public_id: str | None) -> int | None:
    if not public_id:
        return None
    uid = db.scalar(select(OrgUnit.id).where(OrgUnit.public_id == public_id, OrgUnit.is_deleted.is_(False)))
    if uid is None:
        raise NotFound("Organisation not found")
    return uid


def _member(db: Session, public_id: str | None) -> Member | None:
    if not public_id:
        return None
    m = db.scalar(select(Member).where(Member.public_id == public_id, Member.is_deleted.is_(False)))
    if m is None:
        raise NotFound("Member not found")
    return m


def _user(db: Session, public_id: str | None) -> User | None:
    if not public_id:
        return None
    u = db.scalar(select(User).where(User.public_id == public_id, User.is_deleted.is_(False)))
    if u is None:
        raise NotFound("User not found")
    return u


def _latest_instance(db: Session, entity_type: str, entity_id: str) -> str | None:
    return db.scalar(
        select(WorkflowInstance.public_id)
        .where(WorkflowInstance.entity_type == entity_type, WorkflowInstance.entity_id == entity_id)
        .order_by(WorkflowInstance.id.desc())
        .limit(1)
    )


def _audit(
    db: Session,
    auth: Auth,
    request: Request,
    action: str,
    entity: str,
    entity_id: str,
    module: str,
    **kw: Any,
) -> None:
    record_audit(
        db,
        action=action,
        module=module,
        user_id=auth.user.id,
        request=request,
        entity_type=entity,
        entity_id=entity_id,
        **kw,
    )


def _scope(auth: Auth, code: str) -> PermissionScope:
    return auth.permissions.scope(code)


def _date_range(stmt: Select[Any], col: Any, date_from: date | None, date_to: date | None) -> Select[Any]:
    if date_from:
        stmt = stmt.where(col >= date_from)
    if date_to:
        stmt = stmt.where(col <= date_to)
    return stmt


# ============================================================================ activities
def _participants(db: Session, rows: list[ParticipantIn]) -> list[ActivityParticipant]:
    out = []
    for r in rows:
        mem = _member(db, r.member_id)
        out.append(
            ActivityParticipant(
                member_id=mem.id if mem else None,
                name=(r.name or "").strip() or (mem.full_name if mem else ""),
                role=r.role,
            )
        )
    return out


def _activity_fields(db: Session, body: ActivityIn) -> dict[str, Any]:
    data = body.model_dump(exclude={"org_unit_id", "responsible_member_id", "participants"})
    mem = _member(db, body.responsible_member_id)
    data["responsible_member_id"] = mem.id if mem else None
    if mem and not body.responsible_name:
        data["responsible_name"] = mem.full_name
    if data.get("category") and data["category"] not in svc.ACTIVITY_CATEGORIES:
        raise ValidationFailed(details=[{"field": "category", "message": "Unknown category"}])
    return data


def _activity_list_out(a: Activity, refs: Refs) -> ActivityListOut:
    return ActivityListOut(
        id=a.public_id,
        code=a.code,
        title=a.title,
        category=a.category,
        org_unit=refs.unit(a.org_unit_id),
        activity_date=a.activity_date,
        end_date=a.end_date,
        location=a.location,
        responsible=a.responsible_name,
        status=a.status,
        planned_amount=a.planned_amount,
        actual_amount=a.actual_amount,
        participant_count=a.participant_count,
    )


def _activity_out(db: Session, auth: Auth, a: Activity) -> ActivityOut:
    refs = Refs(db)
    mem = db.get(Member, a.responsible_member_id) if a.responsible_member_id else None
    unit = a.org_unit_id
    upd, sub, dele = (
        _scope(auth, c).allows(unit) for c in ("activity.update", "activity.submit", "activity.delete")
    )
    return ActivityOut(
        **_activity_list_out(a, refs).model_dump(),
        description=a.description,
        responsible_member=PersonRef(id=mem.public_id, name=mem.full_name) if mem else None,
        planned_details=a.planned_details,
        actual_details=a.actual_details,
        remarks=a.remarks,
        participants=[
            ParticipantOut(
                member_id=(db.get(Member, p.member_id).public_id if p.member_id else None),  # type: ignore[union-attr]
                name=p.name,
                role=p.role,
            )
            for p in a.participants
        ],
        created_by=refs.user_name(a.created_by),
        created_at=a.created_at,
        submitted_at=a.submitted_at,
        approved_at=a.approved_at,
        completed_at=a.completed_at,
        approval_id=_latest_instance(db, "ACTIVITY", a.public_id),
        can=Actions(
            edit=upd and a.status in EDITABLE,
            submit=sub and a.status in EDITABLE,
            delete=dele and a.status == "DRAFT",
            complete=upd and a.status == "APPROVED",
            cancel=upd and a.status in ("DRAFT", "APPROVED"),
            attach=upd and a.status not in ("REJECTED", "CANCELLED"),
        ),
    )


def _activity_query(
    auth: Auth,
    scope: PermissionScope,
    db: Session,
    q: str | None,
    org_unit: str | None,
    status_: str | None,
    category: str | None,
    date_from: date | None,
    date_to: date | None,
    mine: bool,
) -> Select[Any]:
    stmt = select(Activity).where(Activity.is_deleted.is_(False), scope.filter(Activity.org_unit_id))
    if org_unit == "PARISH":
        stmt = stmt.where(Activity.org_unit_id.is_(None))
    elif org_unit:
        stmt = stmt.where(Activity.org_unit_id == _unit_id(db, org_unit))
    if status_:
        stmt = stmt.where(Activity.status.in_(status_.split(",")))
    if category:
        stmt = stmt.where(Activity.category == category)
    if mine:
        stmt = stmt.where(Activity.created_by == auth.user.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Activity.title.ilike(like), Activity.code.ilike(like), Activity.location.ilike(like))
        )
    return _date_range(stmt, Activity.activity_date, date_from, date_to)


@activities_router.get("/categories", response_model=list[str])
def activity_categories(_: ActView) -> list[str]:
    return list(svc.ACTIVITY_CATEGORIES)


@activities_router.get("", response_model=Page[ActivityListOut])
def list_activities(
    auth: Auth,
    scope: ActView,
    db: TenantSession,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    org_unit: Annotated[str | None, Query(max_length=26, description="Unit id, or PARISH")] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=100)] = None,
    category: Annotated[str | None, Query(max_length=30)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    mine: bool = False,
) -> Page[ActivityListOut]:
    stmt = _activity_query(auth, scope, db, q, org_unit, status_, category, date_from, date_to, mine)
    stmt = apply_sort(
        stmt,
        params.sort,
        {
            "activity_date": Activity.activity_date,
            "title": Activity.title,
            "code": Activity.code,
            "created_at": Activity.created_at,
        },
        [Activity.activity_date.desc(), Activity.id.desc()],
    )
    refs = Refs(db)
    return paginate(db, stmt, params, lambda a: _activity_list_out(a, refs))


@activities_router.get("/export")
def export_activities(
    auth: Auth,
    _: ActExport,
    scope: ActView,
    db: TenantSession,
    request: Request,
    q: Annotated[str | None, Query(max_length=100)] = None,
    org_unit: Annotated[str | None, Query(max_length=26)] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=100)] = None,
    category: Annotated[str | None, Query(max_length=30)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    stmt = _activity_query(auth, scope, db, q, org_unit, status_, category, date_from, date_to, False)
    refs = Refs(db)
    rows = []
    for a in db.scalars(stmt.order_by(Activity.activity_date, Activity.id)):
        u = refs.unit(a.org_unit_id)
        rows.append(
            {
                **_activity_list_out(a, refs).model_dump(),
                "org": u.name if u else "Parish",
                "actual_details": a.actual_details,
            }
        )
    cols = [
        Column("code", "Activity ID", 16),
        Column("activity_date", "Date", 12),
        Column("title", "Activity", 36),
        Column("org", "Organisation", 24),
        Column("category", "Category", 14),
        Column("location", "Location", 20),
        Column("responsible", "Responsible", 20),
        Column("participant_count", "Participants", 12, numeric=True),
        Column("planned_amount", "Planned (₹)", 12, numeric=True),
        Column("actual_amount", "Actual (₹)", 12, numeric=True),
        Column("status", "Status", 12),
    ]
    _audit(
        db,
        auth,
        request,
        "EXPORT",
        "activity",
        "*",
        "activities",
        remarks=f"{len(rows)} rows, {format.value}",
    )
    period = " – ".join(str(d) for d in (date_from, date_to) if d) or None
    return export_table(
        rows,
        cols,
        format,
        title="Activities",
        filename="activities",
        parish_name=auth.tenant.name,
        subtitle=period,
        generated_by=auth.user.full_name,
    )


@activities_router.post("", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
def create_activity(
    body: ActivityIn, request: Request, auth: Auth, scope: ActCreate, db: TenantSession
) -> ActivityOut:
    unit_id = _unit_id(db, body.org_unit_id)
    svc.require_scope(scope, unit_id)
    a = svc.new_activity(db, {**_activity_fields(db, body), "org_unit_id": unit_id}, auth.user.id)
    a.participants = _participants(db, body.participants)
    db.flush()
    _audit(
        db,
        auth,
        request,
        "CREATE",
        "activity",
        a.public_id,
        "activities",
        new={"code": a.code, "title": a.title},
    )
    return _activity_out(db, auth, a)


def _visible_activity(db: Session, auth: Auth, public_id: str) -> Activity:
    a = svc.get_activity(db, public_id)
    if not _scope(auth, "activity.view").allows(a.org_unit_id):
        raise NotFound("Activity not found")
    return a


@activities_router.get("/{activity_id}", response_model=ActivityOut)
def get_activity(activity_id: str, auth: Auth, _: ActView, db: TenantSession) -> ActivityOut:
    return _activity_out(db, auth, _visible_activity(db, auth, activity_id))


@activities_router.put("/{activity_id}", response_model=ActivityOut)
def update_activity(
    activity_id: str, body: ActivityUpdate, request: Request, auth: Auth, scope: ActUpdate, db: TenantSession
) -> ActivityOut:
    a = _visible_activity(db, auth, activity_id)
    svc.require_scope(scope, a.org_unit_id)
    svc.ensure_editable(a.status, "activity")
    unit_id = _unit_id(db, body.org_unit_id)
    if unit_id != a.org_unit_id:
        if a.status != "DRAFT":
            raise Conflict(
                "The organisation cannot change once the activity was submitted", code="NOT_EDITABLE"
            )
        svc.require_scope(scope, unit_id)
        a.org_unit_id = unit_id
    for k, v in _activity_fields(db, body).items():
        setattr(a, k, v)
    old, new = changes(a)
    a.participants = _participants(db, body.participants)
    a.updated_by = auth.user.id
    _audit(db, auth, request, "UPDATE", "activity", a.public_id, "activities", old=old, new=new)
    return _activity_out(db, auth, a)


@activities_router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_activity(
    activity_id: str, request: Request, auth: Auth, scope: ActDelete, db: TenantSession
) -> None:
    a = _visible_activity(db, auth, activity_id)
    svc.require_scope(scope, a.org_unit_id)
    if a.status != "DRAFT":
        raise Conflict("Only draft activities can be deleted; cancel it instead", code="NOT_EDITABLE")
    a.soft_delete(auth.user.id)
    _audit(db, auth, request, "DELETE", "activity", a.public_id, "activities")


@activities_router.post("/{activity_id}/submit", response_model=ActivityOut)
def submit_activity(
    activity_id: str, body: SubmitIn, auth: Auth, scope: ActSubmit, db: TenantSession
) -> ActivityOut:
    a = _visible_activity(db, auth, activity_id)
    svc.require_scope(scope, a.org_unit_id)
    svc.submit_activity(db, auth.tenant, a, auth.user.id, body.comment)
    return _activity_out(db, auth, a)


@activities_router.post("/{activity_id}/complete", response_model=ActivityOut)
def complete_activity(
    activity_id: str, body: CompleteIn, request: Request, auth: Auth, scope: ActUpdate, db: TenantSession
) -> ActivityOut:
    """Record what actually happened after an approved activity took place."""
    a = _visible_activity(db, auth, activity_id)
    svc.require_scope(scope, a.org_unit_id)
    if a.status != "APPROVED":
        raise Conflict("Only approved activities can be completed", code="INVALID_STATE")
    a.actual_details, a.actual_amount = body.actual_details, body.actual_amount
    if body.participant_count is not None:
        a.participant_count = body.participant_count
    if body.participants is not None:
        a.participants = _participants(db, body.participants)
    a.status, a.completed_at, a.updated_by = "COMPLETED", utcnow(), auth.user.id
    _audit(db, auth, request, "COMPLETE", "activity", a.public_id, "activities")
    return _activity_out(db, auth, a)


@activities_router.post("/{activity_id}/cancel", response_model=ActivityOut)
def cancel_activity(
    activity_id: str, body: ReasonIn, request: Request, auth: Auth, scope: ActUpdate, db: TenantSession
) -> ActivityOut:
    a = _visible_activity(db, auth, activity_id)
    svc.require_scope(scope, a.org_unit_id)
    if a.status not in ("DRAFT", "APPROVED"):
        raise Conflict("Withdraw the approval first, then cancel", code="INVALID_STATE")
    a.status = "CANCELLED"
    if body.reason:
        a.remarks = f"{a.remarks}\n" if a.remarks else ""
        a.remarks += f"Cancelled: {body.reason}"
    _audit(db, auth, request, "CANCEL", "activity", a.public_id, "activities", remarks=body.reason)
    return _activity_out(db, auth, a)


@activities_router.get("/{activity_id}/attachments", response_model=list[AttachmentOut])
def activity_files(activity_id: str, auth: Auth, _: ActView, db: TenantSession) -> list[AttachmentOut]:
    a = _visible_activity(db, auth, activity_id)
    return list_attachments(db, auth.tenant, "ACTIVITY", a.id)


@activities_router.post(
    "/{activity_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED
)
async def add_activity_file(
    activity_id: str, auth: Auth, scope: ActUpdate, db: TenantSession, file: Annotated[UploadFile, File()]
) -> AttachmentOut:
    a = _visible_activity(db, auth, activity_id)
    svc.require_scope(scope, a.org_unit_id)
    if a.status in ("REJECTED", "CANCELLED"):
        raise Conflict("Files cannot be added to this activity", code="INVALID_STATE")
    return add_attachment(
        db, auth.tenant, "ACTIVITY", a.id, file.filename or "file", await file.read(), auth.user.id
    )


@activities_router.delete(
    "/{activity_id}/attachments/{file_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def remove_activity_file(
    activity_id: str, file_id: str, auth: Auth, scope: ActUpdate, db: TenantSession
) -> None:
    a = _visible_activity(db, auth, activity_id)
    svc.require_scope(scope, a.org_unit_id)
    svc.ensure_editable(a.status, "activity")
    remove_attachment(db, "ACTIVITY", a.id, file_id, auth.user.id)


# ============================================================================ meetings
def _open_actions(db: Session, meeting_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ActionItem)
            .where(
                ActionItem.meeting_id == meeting_id,
                ActionItem.status.in_(svc.OPEN_ACTION),
                ActionItem.is_deleted.is_(False),
            )
        )
        or 0
    )


def _meeting_list_out(db: Session, m: Meeting, refs: Refs) -> MeetingListOut:
    return MeetingListOut(
        id=m.public_id,
        code=m.code,
        title=m.title,
        meeting_type=m.meeting_type,
        org_unit=refs.unit(m.org_unit_id),
        scheduled_at=m.scheduled_at,
        ends_at=m.ends_at,
        location=m.location,
        status=m.status,
        minutes_status=m.minutes.status if m.minutes else None,
        open_actions=_open_actions(db, m.id),
    )


def _minutes_out(db: Session, auth: Auth, m: Meeting, refs: Refs) -> MinutesOut | None:
    mm = m.minutes
    if mm is None:
        return None
    editable = mm.status in EDITABLE
    return MinutesOut(
        id=mm.public_id,
        status=mm.status,
        summary=mm.summary,
        points=[PointIn(topic=p.topic, discussion=p.discussion) for p in mm.points],
        resolutions=[ResolutionIn(text=r.text, decision=r.decision) for r in mm.resolutions],  # type: ignore[arg-type]
        recorded_by=refs.user_name(mm.recorded_by),
        submitted_at=mm.submitted_at,
        approved_at=mm.approved_at,
        approval_id=_latest_instance(db, "MEETING_MINUTES", mm.public_id),
        can_edit=editable and _scope(auth, "meeting.update").allows(m.org_unit_id),
        can_submit=editable and _scope(auth, "meeting.submit").allows(m.org_unit_id),
    )


def _meeting_out(db: Session, auth: Auth, m: Meeting) -> MeetingOut:
    refs = Refs(db)
    upd = _scope(auth, "meeting.update").allows(m.org_unit_id)
    return MeetingOut(
        **_meeting_list_out(db, m, refs).model_dump(),
        description=m.description,
        agenda=[
            AgendaOut(seq=x.seq, title=x.title, description=x.description, presenter=x.presenter)
            for x in m.agenda
        ],
        called_by=refs.user_name(m.called_by),
        cancel_reason=m.cancel_reason,
        minutes=_minutes_out(db, auth, m, refs),
        can=Actions(
            edit=upd and m.status != "CANCELLED" and not svc.minutes_locked(m),
            delete=_scope(auth, "meeting.delete").allows(m.org_unit_id)
            and m.status == "SCHEDULED"
            and m.minutes is None,
            cancel=upd and m.status == "SCHEDULED",
            attach=upd
            and m.status != "CANCELLED"
            and not (m.minutes is not None and m.minutes.status == "IN_REVIEW"),
        ),
    )


def _visible_meeting(db: Session, auth: Auth, public_id: str) -> Meeting:
    m = svc.get_meeting(db, public_id)
    if not _scope(auth, "meeting.view").allows(m.org_unit_id):
        raise NotFound("Meeting not found")
    return m


def _meeting_query(
    scope: PermissionScope,
    db: Session,
    q: str | None,
    org_unit: str | None,
    status_: str | None,
    when: str | None,
    date_from: date | None,
    date_to: date | None,
) -> Select[Any]:
    stmt = select(Meeting).where(Meeting.is_deleted.is_(False), scope.filter(Meeting.org_unit_id))
    if org_unit == "PARISH":
        stmt = stmt.where(Meeting.org_unit_id.is_(None))
    elif org_unit:
        stmt = stmt.where(Meeting.org_unit_id == _unit_id(db, org_unit))
    if status_:
        stmt = stmt.where(Meeting.status.in_(status_.split(",")))
    now = svc.parish_now(db)
    if when == "upcoming":
        stmt = stmt.where(Meeting.scheduled_at >= now - timedelta(hours=3), Meeting.status != "CANCELLED")
    elif when == "past":
        stmt = stmt.where(Meeting.scheduled_at < now)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Meeting.title.ilike(like), Meeting.code.ilike(like), Meeting.location.ilike(like))
        )
    if date_from:
        stmt = stmt.where(Meeting.scheduled_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(Meeting.scheduled_at <= datetime.combine(date_to, time.max))
    return stmt


@meetings_router.get("", response_model=Page[MeetingListOut])
def list_meetings(
    scope: MtgView,
    db: TenantSession,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    org_unit: Annotated[str | None, Query(max_length=26)] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=60)] = None,
    when: Annotated[str | None, Query(pattern="^(upcoming|past)$")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[MeetingListOut]:
    stmt = _meeting_query(scope, db, q, org_unit, status_, when, date_from, date_to)
    default = (
        [Meeting.scheduled_at, Meeting.id]
        if when == "upcoming"
        else [Meeting.scheduled_at.desc(), Meeting.id]
    )
    stmt = apply_sort(
        stmt, params.sort, {"scheduled_at": Meeting.scheduled_at, "title": Meeting.title}, default
    )
    refs = Refs(db)
    return paginate(db, stmt, params, lambda m: _meeting_list_out(db, m, refs))


@meetings_router.get("/export")
def export_meetings(
    auth: Auth,
    _: MtgExport,
    scope: MtgView,
    db: TenantSession,
    request: Request,
    q: Annotated[str | None, Query(max_length=100)] = None,
    org_unit: Annotated[str | None, Query(max_length=26)] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=60)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    refs = Refs(db)
    rows = []
    for m in db.scalars(
        _meeting_query(scope, db, q, org_unit, status_, None, date_from, date_to).order_by(
            Meeting.scheduled_at
        )
    ):
        u = refs.unit(m.org_unit_id)
        present = sum(a.status == "PRESENT" for a in m.attendance)
        rows.append(
            {
                "code": m.code,
                "when": m.scheduled_at.strftime("%Y-%m-%d %H:%M"),
                "title": m.title,
                "org": u.name if u else "Parish",
                "location": m.location,
                "status": m.status,
                "attendance": f"{present}/{len(m.attendance)}" if m.attendance else "",
                "minutes": m.minutes.status if m.minutes else "",
                "actions": _open_actions(db, m.id),
            }
        )
    cols = [
        Column("code", "Meeting ID", 16),
        Column("when", "Date & time", 17),
        Column("title", "Meeting", 34),
        Column("org", "Organisation", 24),
        Column("location", "Location", 20),
        Column("status", "Status", 11),
        Column("attendance", "Present", 9),
        Column("minutes", "Minutes", 11),
        Column("actions", "Open actions", 12, numeric=True),
    ]
    _audit(
        db, auth, request, "EXPORT", "meeting", "*", "meetings", remarks=f"{len(rows)} rows, {format.value}"
    )
    return export_table(
        rows,
        cols,
        format,
        title="Meetings",
        filename="meetings",
        parish_name=auth.tenant.name,
        generated_by=auth.user.full_name,
    )


def _set_agenda(m: Meeting, body: MeetingIn) -> None:
    m.agenda.clear()
    for i, a in enumerate(body.agenda, start=1):
        m.agenda.append(AgendaItem(seq=i, title=a.title, description=a.description, presenter=a.presenter))


@meetings_router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(
    body: MeetingIn, request: Request, auth: Auth, scope: MtgCreate, db: TenantSession
) -> MeetingOut:
    unit_id = _unit_id(db, body.org_unit_id)
    svc.require_scope(scope, unit_id)
    m = Meeting(
        code=next_meeting_code(db, body.scheduled_at.date()),
        org_unit_id=unit_id,
        title=body.title,
        meeting_type=body.meeting_type,
        scheduled_at=body.scheduled_at,
        ends_at=body.ends_at,
        location=body.location,
        description=body.description,
        status="SCHEDULED",
        called_by=auth.user.id,
        created_by=auth.user.id,
    )
    db.add(m)
    db.flush()
    _set_agenda(m, body)
    db.flush()
    if body.notify and m.scheduled_at > svc.parish_now(db):
        svc.notify_meeting(db, auth.tenant, m, "meeting.scheduled", auth.user.id)
    _audit(
        db,
        auth,
        request,
        "CREATE",
        "meeting",
        m.public_id,
        "meetings",
        new={"code": m.code, "title": m.title},
    )
    return _meeting_out(db, auth, m)


def next_meeting_code(db: Session, on: date) -> str:
    from app.common.sequences import next_code

    return next_code(db, "MEETING", on)


@meetings_router.get("/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: str, auth: Auth, _: MtgView, db: TenantSession) -> MeetingOut:
    return _meeting_out(db, auth, _visible_meeting(db, auth, meeting_id))


@meetings_router.put("/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: str, body: MeetingIn, request: Request, auth: Auth, scope: MtgUpdate, db: TenantSession
) -> MeetingOut:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    if m.status == "CANCELLED" or svc.minutes_locked(m):
        raise Conflict("This meeting can no longer be changed", code="NOT_EDITABLE")
    unit_id = _unit_id(db, body.org_unit_id)
    if unit_id != m.org_unit_id:
        if m.minutes is not None:
            raise Conflict("The organisation cannot change once minutes exist", code="NOT_EDITABLE")
        svc.require_scope(scope, unit_id)
        m.org_unit_id = unit_id
    moved = m.scheduled_at != body.scheduled_at
    for k in ("title", "meeting_type", "scheduled_at", "ends_at", "location", "description"):
        setattr(m, k, getattr(body, k))
    old, new = changes(m)
    _set_agenda(m, body)
    m.updated_by = auth.user.id
    if moved:
        m.reminder_sent_at = None
        if body.notify and m.status == "SCHEDULED" and m.scheduled_at > svc.parish_now(db):
            svc.notify_meeting(db, auth.tenant, m, "meeting.scheduled", auth.user.id)
    _audit(db, auth, request, "UPDATE", "meeting", m.public_id, "meetings", old=old, new=new)
    return _meeting_out(db, auth, m)


@meetings_router.post("/{meeting_id}/cancel", response_model=MeetingOut)
def cancel_meeting(
    meeting_id: str, body: ReasonIn, request: Request, auth: Auth, scope: MtgUpdate, db: TenantSession
) -> MeetingOut:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    if m.status != "SCHEDULED":
        raise Conflict("Only scheduled meetings can be cancelled", code="INVALID_STATE")
    m.status, m.cancel_reason, m.updated_by = "CANCELLED", body.reason, auth.user.id
    if m.scheduled_at > svc.parish_now(db):
        svc.notify_meeting(db, auth.tenant, m, "meeting.cancelled", auth.user.id, reason=body.reason or "")
    _audit(db, auth, request, "CANCEL", "meeting", m.public_id, "meetings", remarks=body.reason)
    return _meeting_out(db, auth, m)


@meetings_router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_meeting(
    meeting_id: str, request: Request, auth: Auth, scope: MtgDelete, db: TenantSession
) -> None:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    if m.status != "SCHEDULED" or m.minutes is not None:
        raise Conflict("Only scheduled meetings without minutes can be deleted", code="NOT_EDITABLE")
    m.soft_delete(auth.user.id)
    _audit(db, auth, request, "DELETE", "meeting", m.public_id, "meetings")


@meetings_router.get("/{meeting_id}/attendance", response_model=AttendanceOut)
def get_attendance(meeting_id: str, auth: Auth, _: MtgView, db: TenantSession) -> AttendanceOut:
    """Recorded attendance, or the organisation's current members as a starting list."""
    m = _visible_meeting(db, auth, meeting_id)
    if m.attendance:
        rows = [_att_row(db, a) for a in m.attendance]
        return AttendanceOut(
            recorded=True, rows=rows, present=sum(r.status == "PRESENT" for r in rows), total=len(rows)
        )
    rows = []
    for x in svc.invitees(db, m):
        mem = db.get(Member, x["member_id"]) if x["member_id"] else None
        fam = db.get(Family, x["family_id"]) if x["family_id"] else None
        rows.append(
            AttendanceRow(
                member_id=mem.public_id if mem else None,
                family_id=fam.public_id if fam else None,
                name=x["name"],
                status="ABSENT",
            )
        )
    return AttendanceOut(recorded=False, rows=rows, present=0, total=len(rows))


def _att_row(db: Session, a: Attendance) -> AttendanceRow:
    mem = db.get(Member, a.member_id) if a.member_id else None
    fam = db.get(Family, a.family_id) if a.family_id else None
    return AttendanceRow(
        member_id=mem.public_id if mem else None,
        family_id=fam.public_id if fam else None,
        name=a.name,
        status=a.status,
        remarks=a.remarks,
    )  # type: ignore[arg-type]


@meetings_router.put("/{meeting_id}/attendance", response_model=AttendanceOut)
def save_attendance(
    meeting_id: str, body: AttendanceIn, request: Request, auth: Auth, scope: MtgUpdate, db: TenantSession
) -> AttendanceOut:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    rows = []
    for r in body.rows:
        mem = _member(db, r.member_id)
        fam = db.scalar(select(Family).where(Family.public_id == r.family_id)) if r.family_id else None
        rows.append(
            {
                "member_id": mem.id if mem else None,
                "family_id": fam.id if fam else None,
                "name": r.name,
                "status": r.status,
                "remarks": r.remarks,
            }
        )
    svc.save_attendance(db, m, rows)
    db.flush()
    _audit(
        db,
        auth,
        request,
        "ATTENDANCE",
        "meeting",
        m.public_id,
        "meetings",
        remarks=f"{sum(r['status'] == 'PRESENT' for r in rows)}/{len(rows)} present",
    )
    return get_attendance(meeting_id, auth, scope, db)


@meetings_router.put("/{meeting_id}/minutes", response_model=MeetingOut)
def save_minutes(
    meeting_id: str, body: MinutesIn, request: Request, auth: Auth, scope: MtgUpdate, db: TenantSession
) -> MeetingOut:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    if m.status == "CANCELLED":
        raise Conflict("The meeting was cancelled", code="INVALID_STATE")
    if m.scheduled_at > svc.parish_now(db) + timedelta(hours=1):
        raise Conflict("Minutes can be recorded once the meeting has taken place", code="MEETING_NOT_HELD")
    mm = m.minutes
    if mm is None:
        mm = MeetingMinutes(
            meeting_id=m.id, status="DRAFT", recorded_by=auth.user.id, created_by=auth.user.id
        )
        db.add(mm)
        m.minutes = mm
    else:
        svc.ensure_editable(mm.status, "minutes")
    mm.summary = body.summary
    mm.points.clear()
    mm.resolutions.clear()
    db.flush()
    for i, p in enumerate(body.points, start=1):
        mm.points.append(DiscussionPoint(seq=i, topic=p.topic, discussion=p.discussion))
    for i, r in enumerate(body.resolutions, start=1):
        mm.resolutions.append(Resolution(seq=i, text=r.text, decision=r.decision))
    mm.updated_by = auth.user.id
    m.status = "HELD"
    db.flush()
    _audit(db, auth, request, "MINUTES", "meeting", m.public_id, "meetings")
    return _meeting_out(db, auth, m)


@meetings_router.post("/{meeting_id}/minutes/submit", response_model=MeetingOut)
def submit_minutes(
    meeting_id: str, body: SubmitIn, auth: Auth, scope: MtgSubmit, db: TenantSession
) -> MeetingOut:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    if m.minutes is None:
        raise ValidationFailed("Write the minutes before submitting them", code="MINUTES_EMPTY")
    svc.submit_minutes(db, auth.tenant, m.minutes, auth.user.id, body.comment)
    return _meeting_out(db, auth, m)


@meetings_router.get("/{meeting_id}/minutes.pdf")
def minutes_pdf(meeting_id: str, auth: Auth, _: MtgView, db: TenantSession) -> Response:
    m = _visible_meeting(db, auth, meeting_id)
    if m.minutes is None:
        raise NotFound("No minutes recorded")
    refs = Refs(db)
    unit = refs.unit(m.org_unit_id)
    actions = db.scalars(
        select(ActionItem)
        .where(ActionItem.meeting_id == m.id, ActionItem.is_deleted.is_(False))
        .order_by(ActionItem.id)
    ).all()
    pdf = render_pdf(
        "minutes.html",
        {
            "title": f"Minutes of Meeting – {m.title}",
            "parish_name": auth.tenant.name,
            "generated_by": auth.user.full_name,
            "meeting": m,
            "organisation": unit.name if unit else auth.tenant.name,
            "when": svc.fmt_when(m.scheduled_at),
            "minutes": m.minutes,
            "present": [a.name for a in m.attendance if a.status == "PRESENT"],
            "excused": [a.name for a in m.attendance if a.status == "EXCUSED"],
            "absent": [a.name for a in m.attendance if a.status == "ABSENT"],
            "actions": actions,
            "recorded_by": refs.user_name(m.minutes.recorded_by),
            "draft": m.minutes.status != "APPROVED",
        },
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(f"minutes-{m.code}.pdf"),
            "Cache-Control": "no-store",
        },
    )


@meetings_router.get("/{meeting_id}/attachments", response_model=list[AttachmentOut])
def meeting_files(meeting_id: str, auth: Auth, _: MtgView, db: TenantSession) -> list[AttachmentOut]:
    m = _visible_meeting(db, auth, meeting_id)
    return list_attachments(db, auth.tenant, "MEETING", m.id)


@meetings_router.post(
    "/{meeting_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED
)
async def add_meeting_file(
    meeting_id: str, auth: Auth, scope: MtgUpdate, db: TenantSession, file: Annotated[UploadFile, File()]
) -> AttachmentOut:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    if svc.minutes_locked(m) and m.minutes and m.minutes.status == "IN_REVIEW":
        raise Conflict("Files cannot be added while the minutes are under review", code="NOT_EDITABLE")
    return add_attachment(
        db, auth.tenant, "MEETING", m.id, file.filename or "file", await file.read(), auth.user.id
    )


@meetings_router.delete(
    "/{meeting_id}/attachments/{file_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def remove_meeting_file(
    meeting_id: str, file_id: str, auth: Auth, scope: MtgUpdate, db: TenantSession
) -> None:
    m = _visible_meeting(db, auth, meeting_id)
    svc.require_scope(scope, m.org_unit_id)
    if svc.minutes_locked(m):
        raise Conflict("Files cannot be removed once the minutes are submitted", code="NOT_EDITABLE")
    remove_attachment(db, "MEETING", m.id, file_id, auth.user.id)


# ============================================================================ action items
def _action_visible_clause(auth: Auth) -> Any:
    scope = _scope(auth, "action_item.view")
    return or_(scope.filter(ActionItem.org_unit_id), ActionItem.owner_user_id == auth.user.id)


def _can_update_action(auth: Auth, a: ActionItem) -> bool:
    return a.owner_user_id == auth.user.id or _scope(auth, "action_item.update").allows(a.org_unit_id)


def _action_out(db: Session, auth: Auth, a: ActionItem, refs: Refs) -> ActionItemOut:
    owner = refs.user(a.owner_user_id)
    src_id = src_title = None
    if a.meeting_id:
        m = db.get(Meeting, a.meeting_id)
        src_id, src_title = (m.public_id, m.title) if m else (None, None)
    elif a.activity_id:
        act = db.get(Activity, a.activity_id)
        src_id, src_title = (act.public_id, act.title) if act else (None, None)
    today = svc.parish_now(db).date()
    return ActionItemOut(
        id=a.public_id,
        code=a.code,
        title=a.title,
        description=a.description,
        org_unit=refs.unit(a.org_unit_id),
        source=SourceRef(type=a.source_type, id=src_id, title=src_title),
        owner=PersonRef(id=owner.public_id, name=owner.full_name) if owner else None,
        owner_name=a.owner_name,
        due_date=a.due_date,
        status=a.status,
        overdue=bool(a.due_date and a.due_date < today and a.status in svc.OPEN_ACTION),
        progress_pct=a.progress_pct,
        completed_on=a.completed_on,
        created_at=a.created_at,
        updates=[
            ProgressOut(
                id=u.public_id,
                text=u.text,
                progress_pct=u.progress_pct,
                status=u.status,
                by=refs.user_name(u.created_by),
                at=u.created_at,
            )
            for u in a.updates
        ],
        can_update=_can_update_action(auth, a) and a.status in svc.OPEN_ACTION,
        can_edit=_scope(auth, "action_item.update").allows(a.org_unit_id) and a.status in svc.OPEN_ACTION,
    )


def _action_query(
    auth: Auth,
    db: Session,
    q: str | None,
    status_: str | None,
    mine: bool,
    overdue: bool,
    org_unit: str | None,
    meeting: str | None,
    activity: str | None,
) -> Select[Any]:
    stmt = select(ActionItem).where(ActionItem.is_deleted.is_(False), _action_visible_clause(auth))
    if mine:
        stmt = stmt.where(ActionItem.owner_user_id == auth.user.id)
    if status_ == "ACTIVE":
        stmt = stmt.where(ActionItem.status.in_(svc.OPEN_ACTION))
    elif status_:
        stmt = stmt.where(ActionItem.status.in_(status_.split(",")))
    if overdue:
        stmt = stmt.where(
            ActionItem.status.in_(svc.OPEN_ACTION), ActionItem.due_date < svc.parish_now(db).date()
        )
    if org_unit == "PARISH":
        stmt = stmt.where(ActionItem.org_unit_id.is_(None))
    elif org_unit:
        stmt = stmt.where(ActionItem.org_unit_id == _unit_id(db, org_unit))
    if meeting:
        stmt = stmt.where(ActionItem.meeting_id == svc.get_meeting(db, meeting).id)
    if activity:
        stmt = stmt.where(ActionItem.activity_id == svc.get_activity(db, activity).id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(ActionItem.title.ilike(like), ActionItem.code.ilike(like), ActionItem.owner_name.ilike(like))
        )
    return stmt


@actions_router.get("", response_model=Page[ActionItemOut])
def list_actions(
    auth: Auth,
    db: TenantSession,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=60)] = None,
    mine: bool = False,
    overdue: bool = False,
    org_unit: Annotated[str | None, Query(max_length=26)] = None,
    meeting: Annotated[str | None, Query(max_length=26)] = None,
    activity: Annotated[str | None, Query(max_length=26)] = None,
) -> Page[ActionItemOut]:
    """Action items in the user's organisations, plus every item the user is responsible for."""
    stmt = _action_query(auth, db, q, status_, mine, overdue, org_unit, meeting, activity)
    stmt = apply_sort(
        stmt,
        params.sort,
        {"due_date": ActionItem.due_date, "created_at": ActionItem.created_at, "title": ActionItem.title},
        [ActionItem.due_date.is_(None), ActionItem.due_date, ActionItem.id],
    )
    refs = Refs(db)
    return paginate(db, stmt, params, lambda a: _action_out(db, auth, a, refs))


@actions_router.get("/summary")
def action_summary(auth: Auth, db: TenantSession) -> dict[str, int]:
    today = svc.parish_now(db).date()
    base = (
        select(func.count())
        .select_from(ActionItem)
        .where(
            ActionItem.owner_user_id == auth.user.id,
            ActionItem.status.in_(svc.OPEN_ACTION),
            ActionItem.is_deleted.is_(False),
        )
    )
    return {"open": db.scalar(base) or 0, "overdue": db.scalar(base.where(ActionItem.due_date < today)) or 0}


@actions_router.get("/export")
def export_actions(
    auth: Auth,
    db: TenantSession,
    request: Request,
    _: Annotated[PermissionScope, Depends(require_perm("action_item.view"))],
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=60)] = None,
    overdue: bool = False,
    org_unit: Annotated[str | None, Query(max_length=26)] = None,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    refs = Refs(db)
    rows = []
    for a in db.scalars(
        _action_query(auth, db, q, status_, False, overdue, org_unit, None, None).order_by(
            ActionItem.due_date, ActionItem.id
        )
    ):
        o = _action_out(db, auth, a, refs)
        rows.append(
            {
                **o.model_dump(),
                "org": o.org_unit.name if o.org_unit else "Parish",
                "owner": o.owner.name if o.owner else (o.owner_name or ""),
                "source": o.source.title or "",
                "state": "OVERDUE" if o.overdue else o.status,
            }
        )
    cols = [
        Column("code", "ID", 14),
        Column("title", "Action item", 40),
        Column("org", "Organisation", 22),
        Column("source", "From", 26),
        Column("owner", "Responsible", 22),
        Column("due_date", "Due", 12),
        Column("state", "Status", 12),
        Column("progress_pct", "Progress %", 10, numeric=True),
    ]
    _audit(db, auth, request, "EXPORT", "action_item", "*", "action_items", remarks=f"{len(rows)} rows")
    return export_table(
        rows,
        cols,
        format,
        title="Action items",
        filename="action-items",
        parish_name=auth.tenant.name,
        generated_by=auth.user.full_name,
    )


@actions_router.post("", response_model=ActionItemOut, status_code=status.HTTP_201_CREATED)
def create_action(body: ActionIn, request: Request, auth: Auth, db: TenantSession) -> ActionItemOut:
    """Create from a meeting (needs meeting.update there), an activity (activity.update) or directly
    (action_item.create for the organisation)."""
    source, meeting_id, activity_id = "MANUAL", None, None
    if body.meeting_id:
        m = _visible_meeting(db, auth, body.meeting_id)
        svc.require_scope(_scope(auth, "meeting.update"), m.org_unit_id)
        source, meeting_id, unit_id = "MEETING", m.id, m.org_unit_id
    elif body.activity_id:
        act = _visible_activity(db, auth, body.activity_id)
        svc.require_scope(_scope(auth, "activity.update"), act.org_unit_id)
        source, activity_id, unit_id = "ACTIVITY", act.id, act.org_unit_id
    else:
        unit_id = _unit_id(db, body.org_unit_id)
        svc.require_scope(_scope(auth, "action_item.create"), unit_id)
    owner = _user(db, body.owner_user_id)
    if owner is None and not (body.owner_name and body.owner_name.strip()):
        raise ValidationFailed(details=[{"field": "owner_user_id", "message": "Choose who is responsible"}])
    a = svc.new_action(
        db,
        auth.tenant,
        {
            "title": body.title,
            "description": body.description,
            "source_type": source,
            "meeting_id": meeting_id,
            "activity_id": activity_id,
            "org_unit_id": unit_id,
            "owner_user_id": owner.id if owner else None,
            "owner_name": body.owner_name or (owner.full_name if owner else None),
            "due_date": body.due_date,
        },
        auth.user.id,
    )
    _audit(db, auth, request, "CREATE", "action_item", a.public_id, "action_items", new={"code": a.code})
    return _action_out(db, auth, a, Refs(db))


def _visible_action(db: Session, auth: Auth, public_id: str) -> ActionItem:
    a = svc.get_action(db, public_id)
    if a.owner_user_id != auth.user.id and not _scope(auth, "action_item.view").allows(a.org_unit_id):
        raise NotFound("Action item not found")
    return a


@actions_router.get("/{action_id}", response_model=ActionItemOut)
def get_action(action_id: str, auth: Auth, db: TenantSession) -> ActionItemOut:
    return _action_out(db, auth, _visible_action(db, auth, action_id), Refs(db))


@actions_router.patch("/{action_id}", response_model=ActionItemOut)
def update_action(
    action_id: str, body: ActionUpdate, request: Request, auth: Auth, db: TenantSession
) -> ActionItemOut:
    a = _visible_action(db, auth, action_id)
    svc.require_scope(_scope(auth, "action_item.update"), a.org_unit_id)
    if a.status not in svc.OPEN_ACTION:
        raise Conflict("This action item is closed", code="INVALID_STATE")
    data = body.model_dump(exclude_unset=True)
    reassigned = False
    if "owner_user_id" in data:
        owner = _user(db, data.pop("owner_user_id"))
        new_id = owner.id if owner else None
        reassigned = new_id is not None and new_id != a.owner_user_id
        a.owner_user_id = new_id
        if owner and not data.get("owner_name"):
            data["owner_name"] = owner.full_name
    for k, v in data.items():
        setattr(a, k, v)
    if "due_date" in data:
        a.last_reminded_on = None
    old, new = changes(a)
    a.updated_by = auth.user.id
    if reassigned:
        svc.notify_assigned(db, auth.tenant, a, auth.user.id)
    _audit(db, auth, request, "UPDATE", "action_item", a.public_id, "action_items", old=old, new=new)
    return _action_out(db, auth, a, Refs(db))


@actions_router.post("/{action_id}/progress", response_model=ActionItemOut)
def add_progress(action_id: str, body: ProgressIn, auth: Auth, db: TenantSession) -> ActionItemOut:
    """Progress note / status change by the person responsible or a coordinator."""
    a = _visible_action(db, auth, action_id)
    if not _can_update_action(auth, a):
        raise PermissionDenied("Only the person responsible or a coordinator can update this item")
    if (
        body.status in ("OPEN", "IN_PROGRESS")
        and a.status in ("DONE", "CANCELLED")
        and not _scope(auth, "action_item.update").allows(a.org_unit_id)
    ):
        raise PermissionDenied("Only a coordinator can reopen this item")
    svc.add_progress(db, a, auth.user.id, text=body.text, progress=body.progress_pct, status=body.status)
    return _action_out(db, auth, a, Refs(db))


# ============================================================================ calendar
@calendar_router.get("", response_model=list[CalendarEvent])
def calendar(
    auth: Auth,
    db: TenantSession,
    start: date,
    end: date,
    org_unit: Annotated[str | None, Query(max_length=26)] = None,
) -> list[CalendarEvent]:
    """Activities and meetings between ``start`` and ``end`` (inclusive, at most 3 months)."""
    if end < start or (end - start).days > 93:
        raise ValidationFailed("Choose a range of at most 3 months", code="INVALID_RANGE")
    unit_id = _unit_id(db, org_unit) if org_unit and org_unit != "PARISH" else None
    refs = Refs(db)
    out: list[CalendarEvent] = []
    act_scope = _scope(auth, "activity.view")
    if act_scope.granted:
        stmt = select(Activity).where(
            Activity.is_deleted.is_(False),
            act_scope.filter(Activity.org_unit_id),
            Activity.status.notin_(("CANCELLED", "REJECTED")),
            Activity.activity_date <= end,
            func.coalesce(Activity.end_date, Activity.activity_date) >= start,
        )
        if org_unit == "PARISH":
            stmt = stmt.where(Activity.org_unit_id.is_(None))
        elif unit_id:
            stmt = stmt.where(Activity.org_unit_id == unit_id)
        for a in db.scalars(stmt):
            out.append(
                CalendarEvent(
                    id=a.public_id,
                    kind="ACTIVITY",
                    title=a.title,
                    start=datetime.combine(a.activity_date, time.min),
                    end=datetime.combine(a.end_date, time.min) if a.end_date else None,
                    all_day=True,
                    status=a.status,
                    org_unit=refs.unit(a.org_unit_id),
                    location=a.location,
                    link=f"/activities/{a.public_id}",
                )
            )
    mtg_scope = _scope(auth, "meeting.view")
    if mtg_scope.granted:
        stmt = select(Meeting).where(
            Meeting.is_deleted.is_(False),
            mtg_scope.filter(Meeting.org_unit_id),
            Meeting.scheduled_at >= datetime.combine(start, time.min),
            Meeting.scheduled_at <= datetime.combine(end, time.max),
        )
        if org_unit == "PARISH":
            stmt = stmt.where(Meeting.org_unit_id.is_(None))
        elif unit_id:
            stmt = stmt.where(Meeting.org_unit_id == unit_id)
        for m in db.scalars(stmt):
            out.append(
                CalendarEvent(
                    id=m.public_id,
                    kind="MEETING",
                    title=m.title,
                    start=m.scheduled_at,
                    end=m.ends_at,
                    all_day=False,
                    status=m.status,
                    org_unit=refs.unit(m.org_unit_id),
                    location=m.location,
                    link=f"/meetings/{m.public_id}",
                )
            )
    return sorted(out, key=lambda e: (e.start, e.kind, e.title))

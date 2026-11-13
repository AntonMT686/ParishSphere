"""Activity reports: organisation-wise activities, monthly summary, meetings, action items, participation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select

from app.modules.activities.models import (
    ActionItem,
    Activity,
    ActivityParticipant,
    Attendance,
    Meeting,
    MeetingMinutes,
)
from app.modules.org_units.models import OrgUnit, OrgUnitType

from .base import DATE_RANGE, ORG_UNIT, Col, Ctx, Param, Result, money, report

ACT_STATUS = Param(
    "status",
    (
        ("APPROVED", "Approved"),
        ("COMPLETED", "Completed"),
        ("IN_REVIEW", "In review"),
        ("DRAFT", "Draft"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
    ),
)
PARISH = "Parish"


def _names(ctx: Ctx) -> dict[int, str]:
    return dict(ctx.db.execute(select(OrgUnit.id, OrgUnit.name)).all())


def _activities(ctx: Ctx, default: str = "fy") -> tuple[list[Activity], date | None, date | None]:
    lo, hi = ctx.range(default)  # type: ignore[arg-type]
    stmt = select(Activity).where(Activity.is_deleted.is_(False), ctx.scope.filter(Activity.org_unit_id))
    if lo:
        stmt = stmt.where(Activity.activity_date >= lo)
    if hi:
        stmt = stmt.where(Activity.activity_date <= hi)
    if ctx.p.status:
        stmt = stmt.where(Activity.status == ctx.p.status)
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(Activity.org_unit_id == u.id)
    if ctx.p.org_type:
        stmt = (
            stmt.join(OrgUnit, OrgUnit.id == Activity.org_unit_id)
            .join(OrgUnitType, OrgUnitType.id == OrgUnit.type_id)
            .where(OrgUnitType.code == ctx.p.org_type)
        )
    return list(ctx.db.scalars(stmt.order_by(Activity.activity_date, Activity.id))), lo, hi


@report(
    "activity_register", "ACTIVITY", "Organisation-wise activities",
    "Activities by organisation with status, participants and amounts. Filter by status for completed "
    "activities, or by organisation type for parish council work.",
    "activity.view", (DATE_RANGE, Param("org_type"), ORG_UNIT, ACT_STATUS),
)  # fmt: skip
def activity_register(ctx: Ctx) -> Result:
    acts, lo, hi = _activities(ctx)
    names = _names(ctx)
    rows = [
        {
            "date": a.activity_date,
            "code": a.code,
            "title": a.title,
            "organisation": names.get(a.org_unit_id or 0, PARISH),
            "category": (a.category or "").replace("_", " ").title(),
            "status": a.status,
            "participants": a.participant_count,
            "planned": money(a.planned_amount) if a.planned_amount is not None else None,
            "actual": money(a.actual_amount) if a.actual_amount is not None else None,
        }
        for a in acts
    ]
    return Result(
        [
            Col("date", "Date", "date"),
            Col("code", "Code"),
            Col("title", "Activity"),
            Col("organisation", "Organisation"),
            Col("category", "Category"),
            Col("status", "Status", "status"),
            Col("participants", "Participants", "number"),
            Col("planned", "Planned ₹", "money"),
            Col("actual", "Actual ₹", "money"),
        ],
        rows,
        subtitle=f"{ctx.range_label(lo, hi)} · {len(rows)} activities",
        totals={
            "title": "Total",
            "participants": sum(r["participants"] or 0 for r in rows),
            "planned": money(sum((r["planned"] or 0) for r in rows)),
            "actual": money(sum((r["actual"] or 0) for r in rows)),
        },
    )


@report(
    "activity_monthly", "ACTIVITY", "Monthly activity summary",
    "Activities per month: planned, approved, completed and cancelled.",
    "activity.view", (DATE_RANGE, ORG_UNIT),
)  # fmt: skip
def activity_monthly(ctx: Ctx) -> Result:
    acts, lo, hi = _activities(ctx)
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in acts:
        k = f"{a.activity_date:%Y-%m}"
        per[k]["total"] += 1
        per[k][a.status] += 1
        per[k]["participants"] += a.participant_count or 0
    rows = [
        {
            "month": date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y"),
            "total": v["total"],
            "pending": v["DRAFT"] + v["IN_REVIEW"] + v["REWORK"],
            "approved": v["APPROVED"],
            "completed": v["COMPLETED"],
            "cancelled": v["CANCELLED"] + v["REJECTED"],
            "participants": v["participants"],
        }
        for k, v in sorted(per.items())
    ]
    keys = ("total", "pending", "approved", "completed", "cancelled", "participants")
    return Result(
        [
            Col("month", "Month"),
            Col("total", "Activities", "number"),
            Col("pending", "Being prepared / in review", "number"),
            Col("approved", "Approved (not yet completed)", "number"),
            Col("completed", "Completed", "number"),
            Col("cancelled", "Cancelled / rejected", "number"),
            Col("participants", "Participants", "number"),
        ],
        rows,
        subtitle=ctx.range_label(lo, hi),
        totals={"month": "Total", **{k: sum(r[k] for r in rows) for k in keys}},
    )


@report(
    "meeting_report", "ACTIVITY", "Meeting report",
    "Meetings with attendance, minutes status and the action items they produced.",
    "meeting.view", (DATE_RANGE, ORG_UNIT),
)  # fmt: skip
def meeting_report(ctx: Ctx) -> Result:
    lo, hi = ctx.range()
    stmt = select(Meeting).where(Meeting.is_deleted.is_(False), ctx.scope.filter(Meeting.org_unit_id))
    if lo:
        stmt = stmt.where(Meeting.scheduled_at >= lo)
    if hi:
        stmt = stmt.where(func.date(Meeting.scheduled_at) <= hi)
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(Meeting.org_unit_id == u.id)
    meetings = list(ctx.db.scalars(stmt.order_by(Meeting.scheduled_at)))
    ids = [m.id for m in meetings] or [-1]
    att: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for mid, st, n in ctx.db.execute(
        select(Attendance.meeting_id, Attendance.status, func.count())
        .where(Attendance.meeting_id.in_(ids))
        .group_by(Attendance.meeting_id, Attendance.status)
    ).all():
        att[mid][st] = n
    minutes = dict(
        ctx.db.execute(
            select(MeetingMinutes.meeting_id, MeetingMinutes.status).where(
                MeetingMinutes.meeting_id.in_(ids), MeetingMinutes.is_deleted.is_(False)
            )
        ).all()
    )
    actions = dict(
        ctx.db.execute(
            select(ActionItem.meeting_id, func.count())
            .where(ActionItem.meeting_id.in_(ids), ActionItem.is_deleted.is_(False))
            .group_by(ActionItem.meeting_id)
        ).all()
    )
    names = _names(ctx)
    rows = [
        {
            "date": m.scheduled_at,
            "code": m.code,
            "title": m.title,
            "organisation": names.get(m.org_unit_id or 0, PARISH),
            "type": m.meeting_type.title(),
            "status": m.status,
            "present": att[m.id]["PRESENT"],
            "absent": att[m.id]["ABSENT"] + att[m.id]["EXCUSED"],
            "minutes": minutes.get(m.id, "—"),
            "actions": actions.get(m.id, 0),
        }
        for m in meetings
    ]
    return Result(
        [
            Col("date", "Date & time", "date"),
            Col("code", "Code"),
            Col("title", "Meeting"),
            Col("organisation", "Organisation"),
            Col("type", "Type"),
            Col("status", "Status", "status"),
            Col("present", "Present", "number"),
            Col("absent", "Absent / excused", "number"),
            Col("minutes", "Minutes", "status"),
            Col("actions", "Action items", "number"),
        ],
        rows,
        subtitle=f"{ctx.range_label(lo, hi)} · {len(rows)} meetings",
    )


@report(
    "pending_action_items", "ACTIVITY", "Pending action items",
    "Open and in-progress action items, overdue ones first.",
    "action_item.view", (ORG_UNIT,),
)  # fmt: skip
def pending_action_items(ctx: Ctx) -> Result:
    stmt = select(ActionItem).where(
        ActionItem.is_deleted.is_(False),
        ActionItem.status.in_(("OPEN", "IN_PROGRESS")),
        ctx.scope.filter(ActionItem.org_unit_id),
    )
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(ActionItem.org_unit_id == u.id)
    today = ctx.today()
    names = _names(ctx)
    items = list(ctx.db.scalars(stmt))
    items.sort(key=lambda a: (a.due_date is None, a.due_date or date.max))
    meetings = dict(
        ctx.db.execute(
            select(Meeting.id, Meeting.title).where(
                Meeting.id.in_([a.meeting_id for a in items if a.meeting_id] or [-1])
            )
        ).all()
    )
    rows = [
        {
            "code": a.code,
            "title": a.title,
            "organisation": names.get(a.org_unit_id or 0, PARISH),
            "source": meetings.get(a.meeting_id or 0) or a.source_type.title(),
            "owner": a.owner_name,
            "due": a.due_date,
            "overdue_days": (today - a.due_date).days if a.due_date and a.due_date < today else None,
            "progress": a.progress_pct,
            "status": "OVERDUE" if a.due_date and a.due_date < today else a.status,
        }
        for a in items
    ]
    overdue = sum(1 for r in rows if r["overdue_days"])
    return Result(
        [
            Col("code", "Code"),
            Col("title", "Action item"),
            Col("organisation", "Organisation"),
            Col("source", "From"),
            Col("owner", "Responsible"),
            Col("due", "Due", "date"),
            Col("overdue_days", "Days overdue", "number"),
            Col("progress", "Progress %", "number"),
            Col("status", "Status", "status"),
        ],
        rows,
        subtitle=f"{len(rows)} pending · {overdue} overdue",
    )


@report(
    "activity_participation", "ACTIVITY", "Activity participation",
    "Completed activities per organisation, with participants recorded and the average turnout.",
    "activity.view", (DATE_RANGE, Param("org_type")),
)  # fmt: skip
def activity_participation(ctx: Ctx) -> Result:
    ctx.p.status = "COMPLETED"
    acts, lo, hi = _activities(ctx)
    named = dict(
        ctx.db.execute(
            select(ActivityParticipant.activity_id, func.count())
            .where(ActivityParticipant.activity_id.in_([a.id for a in acts] or [-1]))
            .group_by(ActivityParticipant.activity_id)
        ).all()
    )
    names = _names(ctx)
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in acts:
        k = names.get(a.org_unit_id or 0, PARISH)
        per[k]["activities"] += 1
        per[k]["participants"] += a.participant_count or 0
        per[k]["named"] += named.get(a.id, 0)
    rows = [
        {
            "organisation": k,
            "activities": v["activities"],
            "participants": v["participants"],
            "named": v["named"],
            "average": round(v["participants"] / v["activities"], 1) if v["activities"] else 0,
        }
        for k, v in sorted(per.items(), key=lambda kv: -kv[1]["participants"])
    ]
    return Result(
        [
            Col("organisation", "Organisation"),
            Col("activities", "Completed activities", "number"),
            Col("participants", "Participants", "number"),
            Col("named", "Named participants", "number"),
            Col("average", "Average per activity", "number"),
        ],
        rows,
        subtitle=ctx.range_label(lo, hi),
        totals={
            "organisation": "Total",
            "activities": sum(r["activities"] for r in rows),
            "participants": sum(r["participants"] for r in rows),
            "named": sum(r["named"] for r in rows),
        },
    )

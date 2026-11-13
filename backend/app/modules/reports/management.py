"""Management reports: pending approvals, user activity, workflow turnaround, committee performance."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from statistics import mean
from typing import Any

from sqlalchemy import func, select

from app.db.base import utcnow
from app.modules.activities.models import ActionItem, Activity, Meeting, MeetingMinutes
from app.modules.core.models import AuditLog
from app.modules.identity.models import User
from app.modules.org_units.models import OrgUnit, OrgUnitType
from app.modules.workflow.models import WorkflowInstance, WorkflowTask
from app.modules.workflow.registry import ENTITY_TYPES

from .base import DATE_RANGE, Col, Ctx, Param, Result, report

ENTITY = Param("status", tuple((k, v.label) for k, v in ENTITY_TYPES.items()))


def _users(ctx: Ctx) -> dict[int, str]:
    return dict(ctx.db.execute(select(User.id, User.full_name)).all())


def _label(entity_type: str) -> str:
    et = ENTITY_TYPES.get(entity_type)
    return et.label if et else entity_type


@report(
    "pending_approvals", "MANAGEMENT", "Pending approvals",
    "Every approval still in progress or returned for rework: stage, who it is waiting with, "
    "and for how long.",
    "workflow.view", (ENTITY,), parish_wide=True,
)  # fmt: skip
def pending_approvals(ctx: Ctx) -> Result:
    stmt = select(WorkflowInstance).where(WorkflowInstance.status.in_(("IN_PROGRESS", "REWORK")))
    if ctx.p.status:
        stmt = stmt.where(WorkflowInstance.entity_type == ctx.p.status)
    insts = list(ctx.db.scalars(stmt.order_by(WorkflowInstance.submitted_at)))
    users = _users(ctx)
    now = utcnow()
    pending: dict[int, list[WorkflowTask]] = defaultdict(list)
    for t in ctx.db.scalars(
        select(WorkflowTask).where(
            WorkflowTask.instance_id.in_([i.id for i in insts] or [-1]), WorkflowTask.status == "PENDING"
        )
    ):
        pending[t.instance_id].append(t)
    rows = []
    for i in insts:
        tasks = pending[i.id]
        stages = i.stages
        due = min((t.due_at for t in tasks if t.due_at), default=None)
        rows.append(
            {
                "type": _label(i.entity_type),
                "title": i.title,
                "stage": stages[i.stage_index]["name"]
                if i.status == "IN_PROGRESS" and i.stage_index < len(stages)
                else "",
                "waiting_with": ", ".join(users.get(t.assignee_id, "") for t in tasks)
                if i.status == "IN_PROGRESS"
                else users.get(i.submitted_by, ""),
                "submitted_by": users.get(i.submitted_by, ""),
                "submitted_at": i.submitted_at,
                "days": (now - i.submitted_at).days,
                "status": "OVERDUE" if due and due < now else i.status,
            }
        )
    overdue = sum(1 for r in rows if r["status"] == "OVERDUE")
    return Result(
        [
            Col("type", "Record"),
            Col("title", "Title"),
            Col("stage", "Stage"),
            Col("waiting_with", "Waiting with"),
            Col("submitted_by", "Submitted by"),
            Col("submitted_at", "Submitted", "date"),
            Col("days", "Days open", "number"),
            Col("status", "Status", "status"),
        ],
        rows,
        subtitle=f"{len(rows)} open · {overdue} overdue",
    )


@report(
    "user_activity", "MANAGEMENT", "User activity",
    "Sign-ins, failed sign-ins and recorded actions per user, from the audit log.",
    "audit.view", (DATE_RANGE,), parish_wide=True,
)  # fmt: skip
def user_activity(ctx: Ctx) -> Result:
    lo, hi = ctx.range("month")
    stmt = select(AuditLog.user_id, AuditLog.action, func.count(), func.max(AuditLog.occurred_at)).where(
        AuditLog.user_id.is_not(None)
    )
    if lo:
        stmt = stmt.where(AuditLog.occurred_at >= datetime.combine(lo, time.min))
    if hi:
        stmt = stmt.where(AuditLog.occurred_at <= datetime.combine(hi, time.max))
    per: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"logins": 0, "failed": 0, "actions": 0, "last": None}
    )
    for uid, action, n, last in ctx.db.execute(stmt.group_by(AuditLog.user_id, AuditLog.action)).all():
        row = per[uid]
        if action == "LOGIN":
            row["logins"] += n
        elif action in ("LOGIN_FAILED", "LOGIN_BLOCKED"):
            row["failed"] += n
        else:
            row["actions"] += n
        row["last"] = max(x for x in (row["last"], last) if x is not None)
    accounts = {u.id: u for u in ctx.db.scalars(select(User).where(User.id.in_(per.keys() or [-1])))}
    rows = [
        {
            "name": accounts[uid].full_name if uid in accounts else f"#{uid}",
            "username": accounts[uid].username if uid in accounts else "",
            "logins": v["logins"],
            "failed": v["failed"],
            "actions": v["actions"],
            "last": v["last"],
            "last_login": accounts[uid].last_login_at if uid in accounts else None,
        }
        for uid, v in sorted(per.items(), key=lambda kv: -(kv[1]["actions"] + kv[1]["logins"]))
    ]
    return Result(
        [
            Col("name", "User"),
            Col("username", "Username"),
            Col("logins", "Sign-ins", "number"),
            Col("failed", "Failed sign-ins", "number"),
            Col("actions", "Recorded actions", "number"),
            Col("last", "Last activity", "date"),
            Col("last_login", "Last sign-in", "date"),
        ],
        rows,
        subtitle=f"{ctx.range_label(lo, hi)} · {len(rows)} active users",
    )


@report(
    "workflow_turnaround", "MANAGEMENT", "Workflow turnaround time",
    "Approvals finished in the period, per record type: outcome, average and longest time to decide, rework.",
    "workflow.view", (DATE_RANGE,), parish_wide=True,
)  # fmt: skip
def workflow_turnaround(ctx: Ctx) -> Result:
    lo, hi = ctx.range()
    stmt = select(WorkflowInstance).where(WorkflowInstance.completed_at.is_not(None))
    if lo:
        stmt = stmt.where(WorkflowInstance.completed_at >= datetime.combine(lo, time.min))
    if hi:
        stmt = stmt.where(WorkflowInstance.completed_at <= datetime.combine(hi, time.max))
    per: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "APPROVED": 0, "REJECTED": 0, "other": 0, "hours": [], "rework": 0}
    )
    for i in ctx.db.scalars(stmt):
        p = per[i.entity_type]
        p["n"] += 1
        p[i.status if i.status in ("APPROVED", "REJECTED") else "other"] += 1
        p["hours"].append((i.completed_at - i.submitted_at).total_seconds() / 3600)  # type: ignore[operator]
        p["rework"] += max(0, i.cycle - 1)
    rows = [
        {
            "type": _label(k),
            "completed": v["n"],
            "approved": v["APPROVED"],
            "rejected": v["REJECTED"],
            "withdrawn": v["other"],
            "avg_days": round(mean(v["hours"]) / 24, 1) if v["hours"] else 0,
            "max_days": round(max(v["hours"]) / 24, 1) if v["hours"] else 0,
            "rework": v["rework"],
        }
        for k, v in sorted(per.items(), key=lambda kv: -kv[1]["n"])
    ]
    return Result(
        [
            Col("type", "Record"),
            Col("completed", "Decided", "number"),
            Col("approved", "Approved", "number"),
            Col("rejected", "Rejected", "number"),
            Col("withdrawn", "Withdrawn", "number"),
            Col("avg_days", "Average days", "number"),
            Col("max_days", "Longest days", "number"),
            Col("rework", "Sent back for rework", "number"),
        ],
        rows,
        subtitle=ctx.range_label(lo, hi),
    )


@report(
    "committee_performance", "MANAGEMENT", "Committee performance",
    "Per organisation: activities completed and planned, meetings held, minutes approved, action items.",
    "activity.view", (DATE_RANGE, Param("org_type")),
)  # fmt: skip
def committee_performance(ctx: Ctx) -> Result:
    lo, hi = ctx.range()
    units = ctx.db.execute(
        select(OrgUnit.id, OrgUnit.name, OrgUnitType.name)
        .join(OrgUnitType, OrgUnitType.id == OrgUnit.type_id)
        .where(OrgUnit.is_deleted.is_(False), OrgUnit.status == "ACTIVE", ctx.scope.filter(OrgUnit.id))
        .where(OrgUnitType.code == ctx.p.org_type if ctx.p.org_type else OrgUnit.id.is_not(None))
    ).all()
    ids = [u for u, _, _ in units] or [-1]
    stats: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def bump(rows: Any, key_of: Any) -> None:
        for unit, key, n in rows:
            stats[unit][key_of(key)] += n

    act = select(Activity.org_unit_id, Activity.status, func.count()).where(
        Activity.org_unit_id.in_(ids), Activity.is_deleted.is_(False)
    )
    if lo:
        act = act.where(Activity.activity_date >= lo)
    if hi:
        act = act.where(Activity.activity_date <= hi)
    bump(ctx.db.execute(act.group_by(Activity.org_unit_id, Activity.status)).all(), lambda s: f"act_{s}")
    mtg = select(Meeting.org_unit_id, Meeting.status, func.count()).where(
        Meeting.org_unit_id.in_(ids), Meeting.is_deleted.is_(False)
    )
    if lo:
        mtg = mtg.where(Meeting.scheduled_at >= datetime.combine(lo, time.min))
    if hi:
        mtg = mtg.where(Meeting.scheduled_at <= datetime.combine(hi, time.max))
    bump(ctx.db.execute(mtg.group_by(Meeting.org_unit_id, Meeting.status)).all(), lambda s: f"mtg_{s}")
    mins = (
        select(Meeting.org_unit_id, MeetingMinutes.status, func.count())
        .join(Meeting, Meeting.id == MeetingMinutes.meeting_id)
        .where(Meeting.org_unit_id.in_(ids), MeetingMinutes.is_deleted.is_(False))
    )
    if lo:
        mins = mins.where(Meeting.scheduled_at >= datetime.combine(lo, time.min))
    if hi:
        mins = mins.where(Meeting.scheduled_at <= datetime.combine(hi, time.max))
    bump(
        ctx.db.execute(mins.group_by(Meeting.org_unit_id, MeetingMinutes.status)).all(), lambda s: f"min_{s}"
    )
    today = ctx.today()
    for unit, status, due in ctx.db.execute(
        select(ActionItem.org_unit_id, ActionItem.status, ActionItem.due_date).where(
            ActionItem.org_unit_id.in_(ids), ActionItem.is_deleted.is_(False)
        )
    ).all():
        if status == "DONE":
            stats[unit]["ai_done"] += 1
        elif status in ("OPEN", "IN_PROGRESS"):
            stats[unit]["ai_open"] += 1
            if due and due < today:
                stats[unit]["ai_overdue"] += 1
    rows = []
    for uid, name, type_name in units:
        s = stats[uid]
        rows.append(
            {
                "organisation": name,
                "type": type_name,
                "completed": s["act_COMPLETED"],
                "planned": s["act_APPROVED"] + s["act_IN_REVIEW"],
                "meetings": s["mtg_HELD"],
                "minutes": s["min_APPROVED"],
                "actions_done": s["ai_done"],
                "actions_open": s["ai_open"],
                "actions_overdue": s["ai_overdue"],
            }
        )
    rows.sort(key=lambda r: (-(r["completed"] + r["meetings"]), r["organisation"]))
    return Result(
        [
            Col("organisation", "Organisation"),
            Col("type", "Type"),
            Col("completed", "Activities completed", "number"),
            Col("planned", "Activities planned", "number"),
            Col("meetings", "Meetings held", "number"),
            Col("minutes", "Minutes approved", "number"),
            Col("actions_done", "Action items done", "number"),
            Col("actions_open", "Action items open", "number"),
            Col("actions_overdue", "Overdue", "number"),
        ],
        rows,
        subtitle=ctx.range_label(lo, hi),
    )

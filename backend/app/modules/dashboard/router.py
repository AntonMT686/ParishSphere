"""One aggregate endpoint for the role dashboards (T14).

The dashboard is permission-driven rather than hard-wired to role names: each section is returned only
when the user holds the permission behind it, and every figure is restricted to the user's scope
(an Anbiyam leader sees their Anbiyam, a society treasurer their society's money). So the Parish Priest
gets the whole picture, the President/Secretary their review queues and committee summaries, the
Treasurer the money, and a parishioner their own family, Anbiyam and donations.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.modules.activities.models import Activity, Meeting, MeetingMinutes
from app.modules.activities.service import parish_now
from app.modules.finance import service as fin
from app.modules.finance.models import FinCategory, FinPeriod, FinTransaction
from app.modules.identity.deps import Auth
from app.modules.org_units.models import OrgUnit, OrgUnitType
from app.modules.parish.models import ParishProfile
from app.modules.people import service as people
from app.modules.people.models import Family, Member, OrgUnitMembership
from app.modules.rbac.service import PermissionScope
from app.modules.workflow.models import WorkflowInstance, WorkflowTask
from app.modules.workflow.registry import ENTITY_TYPES
from app.tenancy.deps import TenantSession

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

LIVE_FAMILY = ("ACTIVE", "PENDING_ANBIYAM")
AGE_BANDS = ((0, 12, "0–12"), (13, 17, "13–17"), (18, 35, "18–35"), (36, 59, "36–59"), (60, 200, "60+"))


class DashRef(BaseModel):
    id: str
    name: str


class DashCount(BaseModel):
    key: str
    label: str
    value: int


class DashTaskItem(BaseModel):
    title: str
    entity_type: str
    entity_label: str
    stage: str | None
    link: str | None
    amount: float | None
    due_at: datetime | None
    overdue: bool


class DashApprovals(BaseModel):
    pending: int
    overdue: int
    finance: int
    by_type: list[DashCount]
    items: list[DashTaskItem]


class DashAnbiyamStat(BaseModel):
    name: str
    families: int
    members: int


class DashPeople(BaseModel):
    families: int
    members: int
    new_families_month: int
    pending_anbiyam: int
    by_anbiyam: list[DashAnbiyamStat]
    age_bands: list[DashCount]
    gender: list[DashCount]


class DashOrgTypeStat(BaseModel):
    code: str
    name: str
    units: int
    members: int
    member_kind: str


class DashMonthPoint(BaseModel):
    key: str  # 2026-11
    income: Decimal
    expense: Decimal


class DashCategoryAmount(BaseModel):
    name: str
    amount: Decimal


class DashPeriodStat(BaseModel):
    key: str
    status: str


class DashFinance(BaseModel):
    fy_label: str
    months: list[DashMonthPoint]
    income_by_category: list[DashCategoryAmount]
    expense_by_category: list[DashCategoryAmount]
    donations_month: Decimal
    donations_fy: Decimal
    pending_entries: int
    periods: list[DashPeriodStat]


class DashActivityItem(BaseModel):
    id: str
    title: str
    date: date
    org_unit: str | None
    status: str


class DashUnitActivity(BaseModel):
    name: str
    completed: int
    planned: int


class DashActivities(BaseModel):
    upcoming: list[DashActivityItem]
    recent: list[DashActivityItem]
    awaiting_report: int
    in_review: int
    by_unit: list[DashUnitActivity]


class DashMeetings(BaseModel):
    upcoming: int
    minutes_in_review: int


class DashHouseholdMember(BaseModel):
    name: str
    relationship: str
    age: int | None


class DashDonation(BaseModel):
    date: date
    category: str | None
    amount: Decimal
    code: str


class DashMe(BaseModel):
    member_code: str
    name: str
    family: DashRef | None
    family_code: str | None
    anbiyam: str | None
    household: list[DashHouseholdMember]
    memberships: list[str]
    donations: list[DashDonation]
    donations_fy: Decimal


class DashboardOut(BaseModel):
    approvals: DashApprovals
    people: DashPeople | None = None
    organisations: list[DashOrgTypeStat] | None = None
    finance: DashFinance | None = None
    activities: DashActivities | None = None
    events: list[DashActivityItem] = []
    meetings: DashMeetings | None = None
    me: DashMe | None = None


# --------------------------------------------------------------------------- helpers


def _age(dob: date | None, today: date) -> int | None:
    if dob is None:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _fy_start(db: Session, today: date) -> date:
    prof = db.get(ParishProfile, 1)
    m = prof.fy_start_month if prof else 4
    return date(today.year if today.month >= m else today.year - 1, m, 1)


def _fy_label(start: date) -> str:
    if start.month == 1:
        return f"FY {start.year}"
    return f"FY {start.year}–{str(start.year + 1)[2:]}"


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _months_back(today: date, n: int) -> list[str]:
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def _unit_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(db.execute(select(OrgUnit.id, OrgUnit.name).where(OrgUnit.id.in_(ids))).all())


# --------------------------------------------------------------------------- sections


def _approvals(db: Session, user_id: int) -> DashApprovals:
    now = utcnow()
    rows = db.execute(
        select(WorkflowTask, WorkflowInstance)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowTask.instance_id)
        .where(
            WorkflowTask.assignee_id == user_id,
            WorkflowTask.status == "PENDING",
            WorkflowInstance.status == "IN_PROGRESS",
        )
        .order_by(WorkflowTask.due_at.is_(None), WorkflowTask.due_at, WorkflowTask.id)
    ).all()
    by_type: dict[str, int] = defaultdict(int)
    items = []
    for task, inst in rows:
        by_type[inst.entity_type] += 1
        if len(items) < 6:
            stages = inst.stages
            items.append(
                DashTaskItem(
                    title=inst.title,
                    entity_type=inst.entity_type,
                    entity_label=ENTITY_TYPES[inst.entity_type].label,
                    stage=stages[inst.stage_index]["name"] if inst.stage_index < len(stages) else None,
                    link=inst.link,
                    amount=inst.context.get("amount"),
                    due_at=task.due_at,
                    overdue=bool(task.due_at and task.due_at < now),
                )
            )
    return DashApprovals(
        pending=len(rows),
        overdue=sum(1 for t, _ in rows if t.due_at and t.due_at < now),
        finance=by_type.get("FIN_TRANSACTION", 0) + by_type.get("FIN_PERIOD", 0),
        by_type=[
            DashCount(key=k, label=ENTITY_TYPES[k].label, value=v)
            for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])
        ],
        items=items,
    )


def _people(db: Session, scope: PermissionScope, today: date) -> DashPeople:
    fam_where = (Family.is_deleted.is_(False), Family.status.in_(LIVE_FAMILY), people.family_scope(scope))
    families = db.scalar(select(func.count()).select_from(Family).where(*fam_where)) or 0
    new_month = (
        db.scalar(
            select(func.count())
            .select_from(Family)
            .where(*fam_where, Family.registered_on >= today.replace(day=1))
        )
        or 0
    )
    pending = (
        db.scalar(select(func.count()).select_from(Family).where(*fam_where, Family.anbiyam_id.is_(None)))
        or 0
    )
    mem_rows = db.execute(
        select(Member.gender, Member.date_of_birth, Family.anbiyam_id)
        .join(Family, Family.id == Member.family_id)
        .where(Member.is_deleted.is_(False), Member.status == "ACTIVE", *fam_where)
    ).all()
    fam_by_unit = dict(
        db.execute(
            select(Family.anbiyam_id, func.count()).where(*fam_where).group_by(Family.anbiyam_id)
        ).all()
    )
    mem_by_unit: dict[int | None, int] = defaultdict(int)
    gender: dict[str, int] = defaultdict(int)
    bands = [0] * len(AGE_BANDS)
    for g, dob, unit in mem_rows:
        mem_by_unit[unit] += 1
        gender[g] += 1
        age = _age(dob, today)
        if age is not None:
            for i, (lo, hi, _) in enumerate(AGE_BANDS):
                if lo <= age <= hi:
                    bands[i] += 1
                    break
    names = _unit_names(db, {u for u in fam_by_unit if u is not None})
    by_anbiyam = sorted(
        (
            DashAnbiyamStat(name=names.get(u, "") if u else "", families=n, members=mem_by_unit.get(u, 0))
            for u, n in fam_by_unit.items()
            if u is not None
        ),
        key=lambda a: (-a.families, a.name),
    )
    return DashPeople(
        families=families,
        members=len(mem_rows),
        new_families_month=new_month,
        pending_anbiyam=pending,
        by_anbiyam=by_anbiyam,
        age_bands=[DashCount(key=lbl, label=lbl, value=bands[i]) for i, (_, _, lbl) in enumerate(AGE_BANDS)],
        gender=[DashCount(key=k, label=k, value=gender.get(k, 0)) for k in ("M", "F") if gender.get(k)],
    )


def _organisations(db: Session, scope: PermissionScope) -> list[DashOrgTypeStat]:
    units = db.execute(
        select(OrgUnit.id, OrgUnit.type_id).where(
            OrgUnit.is_deleted.is_(False), OrgUnit.status == "ACTIVE", scope.filter(OrgUnit.id)
        )
    ).all()
    unit_type = {u: t for u, t in units}
    members = dict(
        db.execute(
            select(OrgUnitMembership.org_unit_id, func.count())
            .where(OrgUnitMembership.left_on.is_(None), OrgUnitMembership.org_unit_id.in_(unit_type.keys()))
            .group_by(OrgUnitMembership.org_unit_id)
        ).all()
    )
    # Anbiyam families are linked on the family itself (families.anbiyam_id), not via memberships.
    for unit, n in db.execute(
        select(Family.anbiyam_id, func.count())
        .where(
            Family.is_deleted.is_(False),
            Family.status.in_(LIVE_FAMILY),
            Family.anbiyam_id.in_(unit_type.keys()),
        )
        .group_by(Family.anbiyam_id)
    ).all():
        members[unit] = members.get(unit, 0) + n
    out = []
    for ty in db.scalars(
        select(OrgUnitType).where(OrgUnitType.is_deleted.is_(False)).order_by(OrgUnitType.sort_order)
    ):
        ids = [u for u, t in unit_type.items() if t == ty.id]
        if not ids:
            continue
        out.append(
            DashOrgTypeStat(
                code=ty.code,
                name=ty.name_plural,
                units=len(ids),
                members=sum(members.get(u, 0) for u in ids),
                member_kind=ty.member_kind,
            )
        )
    return out


def _finance(db: Session, scope: PermissionScope, today: date, periods: bool) -> DashFinance:
    start = _fy_start(db, today)
    keys = _months_back(today, 12)
    first = date(int(keys[0][:4]), int(keys[0][5:]), 1)
    base = (
        FinTransaction.status == "APPROVED",
        FinTransaction.is_deleted.is_(False),
        FinTransaction.kind.in_(("INCOME", "EXPENSE")),
        scope.filter(FinTransaction.org_unit_id),
        FinTransaction.txn_date <= today,
    )
    months = {k: {"INCOME": Decimal(0), "EXPENSE": Decimal(0)} for k in keys}
    for d, kind, amt in db.execute(
        select(FinTransaction.txn_date, FinTransaction.kind, func.sum(FinTransaction.amount))
        .where(*base, FinTransaction.txn_date >= first)
        .group_by(FinTransaction.txn_date, FinTransaction.kind)
    ).all():
        months[_month_key(d)][kind] += Decimal(amt or 0)
    cats: dict[str, list[DashCategoryAmount]] = {"INCOME": [], "EXPENSE": []}
    donations_fy = Decimal(0)
    for kind, code, name, amt in db.execute(
        select(FinTransaction.kind, FinCategory.code, FinCategory.name, func.sum(FinTransaction.amount))
        .join(FinCategory, FinCategory.id == FinTransaction.category_id)
        .where(*base, FinTransaction.txn_date >= start)
        .group_by(FinTransaction.kind, FinCategory.code, FinCategory.name)
    ).all():
        cats[kind].append(DashCategoryAmount(name=name, amount=fin.money(amt)))
        if code == "DONATION":
            donations_fy = fin.money(amt)
    donations_month = fin.money(
        db.scalar(
            select(func.sum(FinTransaction.amount))
            .join(FinCategory, FinCategory.id == FinTransaction.category_id)
            .where(*base, FinCategory.code == "DONATION", FinTransaction.txn_date >= today.replace(day=1))
        )
    )
    pending = (
        db.scalar(
            select(func.count())
            .select_from(FinTransaction)
            .where(
                FinTransaction.status == "IN_REVIEW",
                FinTransaction.is_deleted.is_(False),
                scope.filter(FinTransaction.org_unit_id),
            )
        )
        or 0
    )
    period_rows: list[DashPeriodStat] = []
    if periods:
        got = {
            f"{p.year}-{p.month:02d}": p.status
            for p in db.scalars(select(FinPeriod).where(FinPeriod.year >= first.year - 1))
        }
        period_rows = [DashPeriodStat(key=k, status=got.get(k, "OPEN")) for k in keys[-6:]]
    return DashFinance(
        fy_label=_fy_label(start),
        months=[
            DashMonthPoint(key=k, income=fin.money(v["INCOME"]), expense=fin.money(v["EXPENSE"]))
            for k, v in months.items()
        ],
        income_by_category=sorted(cats["INCOME"], key=lambda c: -c.amount),
        expense_by_category=sorted(cats["EXPENSE"], key=lambda c: -c.amount),
        donations_month=donations_month,
        donations_fy=donations_fy,
        pending_entries=pending,
        periods=period_rows,
    )


def _activity_item(a: Activity, names: dict[int, str]) -> DashActivityItem:
    return DashActivityItem(
        id=a.public_id,
        title=a.title,
        date=a.activity_date,
        org_unit=names.get(a.org_unit_id) if a.org_unit_id else None,
        status=a.status,
    )


def _activities(db: Session, scope: PermissionScope, today: date) -> DashActivities:
    live = (Activity.is_deleted.is_(False), scope.filter(Activity.org_unit_id))
    upcoming = db.scalars(
        select(Activity)
        .where(*live, Activity.status.in_(("APPROVED", "IN_REVIEW")), Activity.activity_date >= today)
        .order_by(Activity.activity_date, Activity.id)
        .limit(6)
    ).all()
    recent = db.scalars(
        select(Activity)
        .where(*live, Activity.status == "COMPLETED")
        .order_by(Activity.activity_date.desc(), Activity.id.desc())
        .limit(6)
    ).all()
    awaiting = (
        db.scalar(
            select(func.count())
            .select_from(Activity)
            .where(*live, Activity.status == "APPROVED", Activity.activity_date < today)
        )
        or 0
    )
    in_review = (
        db.scalar(select(func.count()).select_from(Activity).where(*live, Activity.status == "IN_REVIEW"))
        or 0
    )
    since = today - timedelta(days=365)
    per_unit: dict[int | None, dict[str, int]] = defaultdict(lambda: {"completed": 0, "planned": 0})
    for unit, st, n in db.execute(
        select(Activity.org_unit_id, Activity.status, func.count())
        .where(*live, Activity.activity_date >= since, Activity.status.in_(("APPROVED", "COMPLETED")))
        .group_by(Activity.org_unit_id, Activity.status)
    ).all():
        per_unit[unit]["completed" if st == "COMPLETED" else "planned"] += n
    names = _unit_names(
        db, {a.org_unit_id for a in [*upcoming, *recent] if a.org_unit_id} | {u for u in per_unit if u}
    )
    by_unit = sorted(
        (
            DashUnitActivity(
                name=names.get(u, "") if u else "", completed=v["completed"], planned=v["planned"]
            )
            for u, v in per_unit.items()
        ),
        key=lambda x: -(x.completed + x.planned),
    )[:10]
    return DashActivities(
        upcoming=[_activity_item(a, names) for a in upcoming],
        recent=[_activity_item(a, names) for a in recent],
        awaiting_report=awaiting,
        in_review=in_review,
        by_unit=by_unit,
    )


def _events(db: Session, unit_ids: set[int], today: date) -> list[DashActivityItem]:
    """Approved parish events (and those of the user's own organisations) in the next 60 days."""
    rows = db.scalars(
        select(Activity)
        .where(
            Activity.is_deleted.is_(False),
            Activity.status == "APPROVED",
            Activity.activity_date >= today,
            Activity.activity_date <= today + timedelta(days=60),
            Activity.org_unit_id.is_(None) | Activity.org_unit_id.in_(unit_ids),
        )
        .order_by(Activity.activity_date, Activity.id)
        .limit(6)
    ).all()
    names = _unit_names(db, {a.org_unit_id for a in rows if a.org_unit_id})
    return [_activity_item(a, names) for a in rows]


def _meetings(db: Session, scope: PermissionScope, now: datetime) -> DashMeetings:
    live = (Meeting.is_deleted.is_(False), scope.filter(Meeting.org_unit_id))
    return DashMeetings(
        upcoming=db.scalar(
            select(func.count())
            .select_from(Meeting)
            .where(*live, Meeting.status == "SCHEDULED", Meeting.scheduled_at >= now)
        )
        or 0,
        minutes_in_review=db.scalar(
            select(func.count())
            .select_from(MeetingMinutes)
            .join(Meeting, Meeting.id == MeetingMinutes.meeting_id)
            .where(*live, MeetingMinutes.is_deleted.is_(False), MeetingMinutes.status == "IN_REVIEW")
        )
        or 0,
    )


def _me(db: Session, member_id: int, today: date) -> tuple[DashMe | None, set[int]]:
    m = db.get(Member, member_id)
    if m is None or m.is_deleted:
        return None, set()
    fam = m.family
    names: dict[int, str] = {}
    household: list[DashHouseholdMember] = []
    donations: list[DashDonation] = []
    donations_fy = Decimal(0)
    memberships = db.execute(
        select(OrgUnit.id, OrgUnit.name)
        .join(OrgUnitMembership, OrgUnitMembership.org_unit_id == OrgUnit.id)
        .where(
            OrgUnitMembership.left_on.is_(None),
            (OrgUnitMembership.member_id == m.id) | (OrgUnitMembership.family_id == fam.id),
        )
    ).all()
    unit_ids = {u for u, _ in memberships}
    if fam.anbiyam_id:
        unit_ids.add(fam.anbiyam_id)
        names = _unit_names(db, {fam.anbiyam_id})

    def order(x: Member) -> tuple[bool, date]:
        return (x.relationship_to_head != "HEAD", x.date_of_birth or date.max)

    for x in sorted(fam.members, key=order):
        if not x.is_deleted and x.status == "ACTIVE":
            household.append(
                DashHouseholdMember(
                    name=" ".join(p for p in (x.first_name, x.last_name) if p),
                    relationship=x.relationship_to_head,
                    age=_age(x.date_of_birth, today),
                )
            )
    approved = (
        FinTransaction.family_id == fam.id,
        FinTransaction.kind == "INCOME",
        FinTransaction.status == "APPROVED",
        FinTransaction.is_deleted.is_(False),
    )
    for t, cat in db.execute(
        select(FinTransaction, FinCategory.name)
        .outerjoin(FinCategory, FinCategory.id == FinTransaction.category_id)
        .where(*approved)
        .order_by(FinTransaction.txn_date.desc(), FinTransaction.id.desc())
        .limit(8)
    ).all():
        donations.append(DashDonation(date=t.txn_date, category=cat, amount=fin.money(t.amount), code=t.code))
    donations_fy = fin.money(
        db.scalar(
            select(func.sum(FinTransaction.amount)).where(
                *approved, FinTransaction.txn_date >= _fy_start(db, today)
            )
        )
    )
    return (
        DashMe(
            member_code=m.code,
            name=" ".join(p for p in (m.first_name, m.last_name) if p),
            family=DashRef(id=fam.public_id, name=fam.family_name),
            family_code=fam.code,
            anbiyam=names.get(fam.anbiyam_id) if fam.anbiyam_id else None,
            household=household,
            memberships=sorted(n for _, n in memberships if n not in names.values()),
            donations=donations,
            donations_fy=donations_fy,
        ),
        unit_ids,
    )


@router.get("", response_model=DashboardOut)
def dashboard(auth: Auth, db: TenantSession) -> DashboardOut:
    perms = auth.permissions
    now = parish_now(db)
    today = now.date()
    out = DashboardOut(approvals=_approvals(db, auth.user.id))
    if (s := perms.scope("family.view")).granted:
        out.people = _people(db, s, today)
    if (s := perms.scope("org_unit.view")).granted:
        out.organisations = _organisations(db, s)
    fin_scope = perms.scope("finance.view")
    if not fin_scope.granted:
        fin_scope = perms.scope("finance.view_summary")
    if fin_scope.granted:
        out.finance = _finance(db, fin_scope, today, perms.scope("finance_period.view").parish_wide)
    if (s := perms.scope("activity.view")).granted:
        out.activities = _activities(db, s, today)
    if (s := perms.scope("meeting.view")).granted:
        out.meetings = _meetings(db, s, now)
    units: set[int] = set()
    if auth.user.member_id:
        out.me, units = _me(db, auth.user.member_id, today)
    out.events = _events(db, units | set(perms.scope("activity.view").org_unit_ids), today)
    return out

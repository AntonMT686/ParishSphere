"""Global search (``GET /search``): one box for families, members, organisations, activities, meetings,
finance entries, notices and users. Every group is permission- and scope-checked exactly like its own
list page, so search never reveals a record its list would hide. Each group returns a few best matches
(exact code first) plus a total, with a link to the record and to the filtered list.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.modules.activities.models import Activity, Meeting
from app.modules.activities.service import parish_now
from app.modules.finance.models import FinTransaction
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.notices import service as notices
from app.modules.notices.models import Notice
from app.modules.org_units.models import OrgUnit
from app.modules.people import service as people
from app.modules.people.models import Family, Member
from app.tenancy.deps import TenantSession

router = APIRouter(prefix="/search", tags=["search"])

GROUPS = ("families", "members", "organisations", "activities", "meetings", "finance", "notices", "users")


class SearchHit(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    code: str | None = None
    status: str | None = None
    link: str


class SearchGroup(BaseModel):
    key: str
    total: int
    more_link: str | None
    hits: list[SearchHit]


class SearchOut(BaseModel):
    q: str
    groups: list[SearchGroup]


def _units(db: Session, ids: set[int | None]) -> dict[int, str]:
    clean = {i for i in ids if i}
    if not clean:
        return {}
    return dict(db.execute(select(OrgUnit.id, OrgUnit.name).where(OrgUnit.id.in_(clean))).all())


def _run(db: Session, stmt: Select[Any], code_col: Any, term: str, limit: int) -> tuple[int, list[Any]]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    if not total:
        return 0, []
    exact = case((func.lower(code_col) == term.lower(), 0), else_=1)
    return total, list(db.scalars(stmt.order_by(exact).limit(limit)))


def search(db: Session, auth: Auth, q: str, limit: int, only: str | None) -> list[SearchGroup]:
    perms = auth.permissions
    term = q.strip()
    like = f"%{term}%"
    name = f"%{people.normalize_name(term)}%"
    digits = people.phone_digits(term)
    enc = term.replace(" ", "+")
    out: list[SearchGroup] = []

    def want(key: str) -> bool:
        return only in (None, key)

    def add(key: str, total: int, hits: list[SearchHit], more: str | None) -> None:
        if total:
            out.append(SearchGroup(key=key, total=total, hits=hits, more_link=more))

    if want("families") and (s := perms.scope("family.view")).granted:
        conds = [Family.code.ilike(like), Family.search_name.like(name), Family.family_name_local.ilike(like)]
        if digits and len(digits) >= 4:
            conds.append(Family.phone_digits.like(f"%{digits}%"))
        stmt = select(Family).where(Family.is_deleted.is_(False), people.family_scope(s), or_(*conds))
        total, rows = _run(db, stmt, Family.code, term, limit)
        names = _units(db, {f.anbiyam_id for f in rows})
        add(
            "families",
            total,
            [
                SearchHit(
                    id=f.public_id,
                    title=f.family_name,
                    code=f.code,
                    status=f.status,
                    subtitle=" · ".join(x for x in (names.get(f.anbiyam_id or 0), f.city) if x) or None,
                    link=f"/families/{f.public_id}",
                )
                for f in rows
            ],
            f"/families?q={enc}",
        )

    if want("members") and (s := perms.scope("member.view")).granted:
        conds = [Member.code.ilike(like), Member.search_name.like(name), Member.name_local.ilike(like)]
        if digits and len(digits) >= 4:
            conds.append(Member.phone_digits.like(f"%{digits}%"))
        stmt = (
            select(Member)
            .join(Family, Family.id == Member.family_id)
            .where(
                Member.is_deleted.is_(False),
                Family.is_deleted.is_(False),
                people.family_scope(s),
                or_(*conds),
            )
        )
        total, rows = _run(db, stmt, Member.code, term, limit)
        add(
            "members",
            total,
            [
                SearchHit(
                    id=m.public_id,
                    title=" ".join(p for p in (m.first_name, m.last_name) if p),
                    code=m.code,
                    status=m.status,
                    subtitle=f"{m.family.family_name} · {m.family.code}",
                    link=f"/families/{m.family.public_id}?member={m.public_id}",
                )
                for m in rows
            ],
            f"/members?q={enc}",
        )

    if want("organisations") and (s := perms.scope("org_unit.view")).granted:
        stmt = select(OrgUnit).where(
            OrgUnit.is_deleted.is_(False),
            or_(OrgUnit.name.ilike(like), OrgUnit.code.ilike(like), OrgUnit.name_local.ilike(like)),
        )
        total, rows = _run(db, stmt, OrgUnit.code, term, limit)
        add(
            "organisations",
            total,
            [
                SearchHit(
                    id=u.public_id,
                    title=u.name,
                    code=u.code,
                    status=u.status,
                    subtitle=u.type.name,
                    link=f"/org/units/{u.public_id}",
                )
                for u in rows
            ],
            None,
        )

    if want("activities") and (s := perms.scope("activity.view")).granted:
        stmt = select(Activity).where(
            Activity.is_deleted.is_(False),
            s.filter(Activity.org_unit_id),
            or_(Activity.title.ilike(like), Activity.code.ilike(like), Activity.location.ilike(like)),
        )
        total, rows = _run(db, stmt, Activity.code, term, limit)
        names = _units(db, {a.org_unit_id for a in rows})
        add(
            "activities",
            total,
            [
                SearchHit(
                    id=a.public_id,
                    title=a.title,
                    code=a.code,
                    status=a.status,
                    subtitle=" · ".join(
                        x for x in (a.activity_date.strftime("%d %b %Y"), names.get(a.org_unit_id or 0)) if x
                    ),
                    link=f"/activities/{a.public_id}",
                )
                for a in rows
            ],
            f"/activities?q={enc}",
        )

    if want("meetings") and (s := perms.scope("meeting.view")).granted:
        stmt = select(Meeting).where(
            Meeting.is_deleted.is_(False),
            s.filter(Meeting.org_unit_id),
            or_(Meeting.title.ilike(like), Meeting.code.ilike(like), Meeting.location.ilike(like)),
        )
        total, rows = _run(db, stmt, Meeting.code, term, limit)
        names = _units(db, {m.org_unit_id for m in rows})
        add(
            "meetings",
            total,
            [
                SearchHit(
                    id=m.public_id,
                    title=m.title,
                    code=m.code,
                    status=m.status,
                    subtitle=" · ".join(
                        x
                        for x in (m.scheduled_at.strftime("%d %b %Y, %H:%M"), names.get(m.org_unit_id or 0))
                        if x
                    ),
                    link=f"/meetings/{m.public_id}",
                )
                for m in rows
            ],
            f"/meetings?q={enc}",
        )

    if want("finance") and (s := perms.scope("finance.view")).granted:
        stmt = select(FinTransaction).where(
            FinTransaction.is_deleted.is_(False),
            s.filter(FinTransaction.org_unit_id),
            or_(
                FinTransaction.code.ilike(like),
                FinTransaction.description.ilike(like),
                FinTransaction.payer_payee.ilike(like),
                FinTransaction.reference_no.ilike(like),
            ),
        )
        total, rows = _run(db, stmt, FinTransaction.code, term, limit)
        add(
            "finance",
            total,
            [
                SearchHit(
                    id=t.public_id,
                    title=t.description,
                    code=t.code,
                    status=t.status,
                    subtitle=f"{t.txn_date.strftime('%d %b %Y')} · {t.kind.title()} · ₹{t.amount:,.2f}",
                    link=f"/finance/transactions/{t.public_id}",
                )
                for t in rows
            ],
            f"/finance/transactions?q={enc}",
        )

    if want("notices") and perms.scope("notice.view").granted:
        manage = perms.scope("notice.update")
        now = parish_now(db)
        cond = or_(Notice.title.ilike(like), Notice.code.ilike(like), Notice.title_local.ilike(like))
        visible = or_(notices.live_clause(now), Notice.created_by == auth.user.id)
        if manage.granted:
            visible = or_(visible, manage.filter(Notice.org_unit_id))
        rows_all = list(
            db.scalars(
                select(Notice)
                .where(Notice.is_deleted.is_(False), cond, visible)
                .order_by(Notice.publish_at.desc().nulls_last(), Notice.id.desc())
                .limit(200)
            )
        )
        units = notices.user_unit_ids(db, auth.user.id)
        rows = [
            n
            for n in rows_all
            if manage.allows(n.org_unit_id)
            or n.created_by == auth.user.id
            or (notices.state(n, now) == "LIVE" and notices.audience_ok(n, units))
        ]
        add(
            "notices",
            len(rows),
            [
                SearchHit(
                    id=n.public_id,
                    title=n.title,
                    code=n.code,
                    status=notices.state(n, now),
                    subtitle=n.category.title(),
                    link=f"/notices/{n.public_id}",
                )
                for n in rows[:limit]
            ],
            "/notices",
        )

    if want("users") and perms.scope("user.view").parish_wide:
        stmt = select(User).where(
            User.is_deleted.is_(False),
            or_(User.full_name.ilike(like), User.username.ilike(like), User.email.ilike(like)),
        )
        total, rows = _run(db, stmt, User.username, term, limit)
        add(
            "users",
            total,
            [
                SearchHit(
                    id=u.public_id,
                    title=u.full_name,
                    code=u.username,
                    status="ACTIVE" if u.is_active else "INACTIVE",
                    subtitle=u.email,
                    link=f"/admin/users?open={u.public_id}",
                )
                for u in rows
            ],
            "/admin/users",
        )
    return out


@router.get("", response_model=SearchOut)
def global_search(
    auth: Auth,
    db: TenantSession,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    group: Annotated[str | None, Query(pattern="^(" + "|".join(GROUPS) + ")$")] = None,
) -> SearchOut:
    return SearchOut(q=q, groups=search(db, auth, q, limit, group))

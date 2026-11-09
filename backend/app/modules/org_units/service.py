"""Organisation services: seeding, tree traversal, unit lifecycle and office-bearer terms.

Office bearers are the bridge to RBAC: appointing a user to a position that maps to a role creates a
role assignment (scoped to the unit, or parish-wide for parish roles such as Parish Secretary);
ending the term ends that assignment. Workflows can then find "the Society President" through RBAC.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.modules.identity.models import User
from app.modules.org_units.models import OrgUnit, OrgUnitOfficeBearer, OrgUnitPosition, OrgUnitType
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.rbac.service import assign_role, register_org_unit_resolver, role_by_code
from app.tenancy.seed import register_seeder

# ----------------------------------------------------------------------------- defaults
_OFFICERS = (
    ("PRESIDENT", "President", "தலைவர்"),
    ("SECRETARY", "Secretary", "செயலாளர்"),
    ("TREASURER", "Treasurer", "பொருளாளர்"),
)


@dataclass(frozen=True)
class TypeDef:
    code: str
    name: str
    plural: str
    name_local: str
    prefix: str
    member_kind: str
    allow_multiple: bool
    positions: tuple[tuple[str, str, str, str | None, int | None], ...]  # code, name, local, role, max
    description: str


def _std(president_role: str) -> tuple[tuple[str, str, str, str | None, int | None], ...]:
    roles = {
        "PRESIDENT": president_role,
        "SECRETARY": "COMMITTEE_SECRETARY",
        "TREASURER": "COMMITTEE_TREASURER",
    }
    return (
        *((c, n, t, roles[c], 1) for c, n, t in _OFFICERS),
        ("VICE_PRESIDENT", "Vice President", "துணைத் தலைவர்", None, 1),
        ("JOINT_SECRETARY", "Joint Secretary", "இணைச் செயலாளர்", None, 1),
        ("EXECUTIVE_MEMBER", "Executive Member", "செயற்குழு உறுப்பினர்", None, None),
    )


DEFAULT_TYPES: tuple[TypeDef, ...] = (
    TypeDef(
        "COUNCIL",
        "Parish Council",
        "Parish Council",
        "பங்குப் பேரவை",
        "PC",
        "MEMBER",
        False,
        (
            ("PRESIDENT", "President", "தலைவர்", "PARISH_PRESIDENT", 1),
            ("VICE_PRESIDENT", "Vice President", "துணைத் தலைவர்", None, 1),
            ("SECRETARY", "Secretary", "செயலாளர்", "PARISH_SECRETARY", 1),
            ("TREASURER", "Treasurer", "பொருளாளர்", "PARISH_TREASURER", 1),
            ("COMMITTEE_REPRESENTATIVE", "Committee Representative", "குழுப் பிரதிநிதி", None, None),
            ("COUNCIL_MEMBER", "Council Member", "பேரவை உறுப்பினர்", None, None),
        ),
        "The Parish Council (Peravai) – the parish's governing body.",
    ),
    TypeDef(
        "COMMITTEE",
        "Committee",
        "Committees",
        "குழு",
        "CMT",
        "MEMBER",
        True,
        _std("COMMITTEE_PRESIDENT"),
        "Parish committees (liturgy, finance, building, festival …).",
    ),
    TypeDef(
        "ANBIYAM",
        "Anbiyam",
        "Anbiyam",
        "அன்பியம்",
        "ANB",
        "FAMILY",
        True,
        _std("ANBIYAM_LEADER"),
        "Basic Christian Communities; every family belongs to one Anbiyam.",
    ),
    TypeDef(
        "SABAI",
        "Sabai",
        "Sabai",
        "சபை",
        "SAB",
        "MEMBER",
        True,
        _std("SABAI_LEADER"),
        "Sabai / congregations.",
    ),
    TypeDef(
        "SOCIETY",
        "Society",
        "Societies",
        "சங்கம்",
        "SOC",
        "MEMBER",
        True,
        _std("SOCIETY_LEADER"),
        "Youth, Women's, Men's, Children's, Choir, Legion of Mary and other societies.",
    ),
    TypeDef(
        "ASSOCIATION",
        "Association",
        "Associations",
        "கழகம்",
        "ASN",
        "MEMBER",
        True,
        _std("COMMITTEE_PRESIDENT"),
        "Other parish associations.",
    ),
)


@register_seeder("org_units.types", order=30)
def seed_org_unit_types(session: Session, _: dict[str, Any]) -> None:
    """Insert missing default types/positions (idempotent; parish edits are never overwritten)."""
    roles = {r.code: r for r in session.scalars(select(Role))}
    for order, td in enumerate(DEFAULT_TYPES, start=1):
        t = session.scalars(select(OrgUnitType).where(OrgUnitType.code == td.code)).first()
        if t is None:
            t = OrgUnitType(
                code=td.code,
                name=td.name,
                name_plural=td.plural,
                name_local=td.name_local,
                description=td.description,
                member_kind=td.member_kind,
                code_prefix=td.prefix,
                allow_multiple_units=td.allow_multiple,
                is_system=True,
                sort_order=order * 10,
            )
            session.add(t)
            session.flush()
            for porder, (code, name, local, role_code, max_holders) in enumerate(td.positions, start=1):
                role = roles.get(role_code) if role_code else None
                session.add(
                    OrgUnitPosition(
                        type_id=t.id,
                        code=code,
                        name=name,
                        name_local=local,
                        role_id=role.id if role else None,
                        max_holders=max_holders,
                        sort_order=porder * 10,
                    )
                )


# ----------------------------------------------------------------------------- tree
def _parent_map(session: Session) -> dict[int, int | None]:
    return dict(
        session.execute(select(OrgUnit.id, OrgUnit.parent_id).where(OrgUnit.is_deleted.is_(False))).all()
    )


def descendants(session: Session, ids: set[int]) -> dict[int, set[int]]:
    children: dict[int | None, set[int]] = defaultdict(set)
    for uid, parent in _parent_map(session).items():
        children[parent].add(uid)
    out: dict[int, set[int]] = {}
    for root in ids:
        seen, stack = {root}, [root]
        while stack:
            for child in children.get(stack.pop(), ()):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        out[root] = seen
    return out


def ancestors(session: Session, ids: set[int]) -> dict[int, set[int]]:
    parents = _parent_map(session)
    out: dict[int, set[int]] = {}
    for start in ids:
        seen, cur = {start}, parents.get(start)
        while cur is not None and cur not in seen:
            seen.add(cur)
            cur = parents.get(cur)
        out[start] = seen
    return out


def _resolve(session: Session, public_id: str) -> int | None:
    return session.scalars(
        select(OrgUnit.id).where(OrgUnit.public_id == public_id, OrgUnit.is_deleted.is_(False))
    ).first()


def _public_id(session: Session, unit_id: int) -> str | None:
    return session.scalars(select(OrgUnit.public_id).where(OrgUnit.id == unit_id)).first()


register_org_unit_resolver(_resolve, _public_id, descendants, ancestors)


# ----------------------------------------------------------------------------- lookups
def get_type(session: Session, code_or_id: str) -> OrgUnitType:
    t = session.scalars(
        select(OrgUnitType).where(
            (OrgUnitType.code == code_or_id.upper()) | (OrgUnitType.public_id == code_or_id),
            OrgUnitType.is_deleted.is_(False),
        )
    ).first()
    if t is None:
        raise NotFound("Organisation type not found")
    return t


def get_unit(session: Session, public_id: str) -> OrgUnit:
    u = session.scalars(
        select(OrgUnit).where(OrgUnit.public_id == public_id, OrgUnit.is_deleted.is_(False))
    ).first()
    if u is None:
        raise NotFound()
    return u


def next_unit_code(session: Session, t: OrgUnitType) -> str:
    n = (session.scalar(select(func.count()).select_from(OrgUnit).where(OrgUnit.type_id == t.id)) or 0) + 1
    while True:
        code = f"{t.code_prefix}-{n:03d}"
        if session.scalars(select(OrgUnit.id).where(OrgUnit.code == code)).first() is None:
            return code
        n += 1


def validate_parent(session: Session, unit: OrgUnit | None, parent: OrgUnit | None) -> None:
    if parent is None:
        return
    if parent.status != "ACTIVE":
        raise ValidationFailed(
            details=[{"field": "parent_id", "message": "Parent organisation is not active"}]
        )
    if unit is not None and unit.id in ancestors(session, {parent.id})[parent.id]:
        raise ValidationFailed(
            "An organisation cannot be placed under itself or one of its sub-units",
            code="ORG_UNIT_CYCLE",
            details=[{"field": "parent_id", "message": "Would create a cycle"}],
        )


def ensure_single_unit(session: Session, t: OrgUnitType, excluding: int | None = None) -> None:
    if t.allow_multiple_units:
        return
    stmt = select(OrgUnit.id).where(OrgUnit.type_id == t.id, OrgUnit.is_deleted.is_(False))
    if excluding is not None:
        stmt = stmt.where(OrgUnit.id != excluding)
    if session.scalars(stmt).first() is not None:
        raise Conflict(f"A parish has only one {t.name}", code="SINGLE_UNIT_TYPE")


# ----------------------------------------------------------------------------- office bearers
def current_bearers_stmt(unit_id: int, day: date | None = None):  # type: ignore[no-untyped-def]
    from sqlalchemy import or_

    day = day or date.today()
    return select(OrgUnitOfficeBearer).where(
        OrgUnitOfficeBearer.org_unit_id == unit_id,
        OrgUnitOfficeBearer.ended_at.is_(None),
        OrgUnitOfficeBearer.valid_from <= day,
        or_(OrgUnitOfficeBearer.valid_to.is_(None), OrgUnitOfficeBearer.valid_to >= day),
    )


def appoint(
    session: Session,
    unit: OrgUnit,
    position: OrgUnitPosition,
    *,
    user: User | None,
    holder_name: str | None,
    member_id: int | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    actor_id: int | None = None,
    remarks: str | None = None,
) -> OrgUnitOfficeBearer:
    if position.type_id != unit.type_id:
        raise ValidationFailed(
            details=[{"field": "position_code", "message": "Position belongs to another type"}]
        )
    if unit.status != "ACTIVE":
        raise Conflict("Cannot appoint office bearers to an inactive organisation", code="INVALID_STATE")
    if user is None and not holder_name:
        raise ValidationFailed(details=[{"field": "holder_name", "message": "Select a user or enter a name"}])
    if user is not None and (not user.is_active or user.is_deleted):
        raise ValidationFailed(details=[{"field": "user_id", "message": "User is not active"}])
    valid_from = valid_from or date.today()
    if valid_to is not None and valid_to < valid_from:
        raise ValidationFailed(
            details=[{"field": "valid_to", "message": "Must be on or after the start date"}]
        )
    current = list(
        session.scalars(
            current_bearers_stmt(unit.id, valid_from).where(OrgUnitOfficeBearer.position_id == position.id)
        )
    )
    if user is not None and any(b.user_id == user.id for b in current):
        raise Conflict("This person already holds this position", code="ALREADY_OFFICE_BEARER")
    if position.max_holders is not None and len(current) >= position.max_holders:
        raise Conflict(
            f"{position.name} already has {len(current)} holder(s); end the current term first",
            code="POSITION_FULL",
        )
    bearer = OrgUnitOfficeBearer(
        org_unit_id=unit.id,
        position_id=position.id,
        user_id=user.id if user else None,
        member_id=member_id,
        holder_name=holder_name or (user.full_name if user else ""),
        valid_from=valid_from,
        valid_to=valid_to,
        created_by=actor_id,
        remarks=remarks,
    )
    if user is not None and position.role_id is not None:
        role = session.get(Role, position.role_id)
        if role is not None and not role.is_deleted:
            scope = None if role.scope_type == "PARISH" else unit.id
            existing = session.scalars(
                select(UserRoleAssignment).where(
                    UserRoleAssignment.user_id == user.id,
                    UserRoleAssignment.role_id == role.id,
                    UserRoleAssignment.ended_at.is_(None),
                    UserRoleAssignment.org_unit_id.is_(None)
                    if scope is None
                    else UserRoleAssignment.org_unit_id == scope,
                )
            ).first()
            if existing is None:
                a = assign_role(
                    session,
                    user,
                    role,
                    org_unit_id=scope,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    assigned_by=actor_id,
                    remarks=f"{position.name}, {unit.name}",
                )
                bearer.role_assignment_id = a.id
    session.add(bearer)
    session.flush()
    return bearer


def end_term(
    session: Session, bearer: OrgUnitOfficeBearer, *, end_date: date | None, actor_id: int | None
) -> None:
    if bearer.ended_at is not None:
        raise Conflict("This term has already ended", code="INVALID_STATE")
    end_date = end_date or date.today()
    if end_date < bearer.valid_from:
        raise ValidationFailed(details=[{"field": "end_date", "message": "Before the start of the term"}])
    now = utcnow()
    bearer.valid_to = end_date
    bearer.ended_at, bearer.ended_by = now, actor_id
    if bearer.role_assignment_id is not None:
        a = session.get(UserRoleAssignment, bearer.role_assignment_id)
        if a is not None and a.ended_at is None:
            if a.role.code == "PARISH_ADMIN":  # never happens via positions, but stay safe
                from app.modules.rbac.service import ensure_not_last_admin

                ensure_not_last_admin(session, excluding_assignment=a.id)
            # The office ends at the end of end_date; the role is ended now if that date has passed.
            a.valid_to = end_date
            if end_date <= date.today():
                a.ended_at, a.ended_by = now, actor_id


def end_all_terms(session: Session, unit: OrgUnit, actor_id: int | None) -> int:
    yesterday = date.today() - timedelta(days=1)
    n = 0
    for b in session.scalars(
        select(OrgUnitOfficeBearer).where(
            OrgUnitOfficeBearer.org_unit_id == unit.id, OrgUnitOfficeBearer.ended_at.is_(None)
        )
    ):
        end_term(session, b, end_date=max(yesterday, b.valid_from), actor_id=actor_id)
        n += 1
    return n


def resolve_role_for_position(session: Session, role_code: str | None) -> int | None:
    if not role_code:
        return None
    role = role_by_code(session, role_code)
    if role is None:
        raise ValidationFailed(details=[{"field": "role_code", "message": "Unknown role"}])
    return role.id

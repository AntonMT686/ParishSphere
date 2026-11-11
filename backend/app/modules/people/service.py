"""Family & member register business rules.

All operations keep history: members are never physically moved without a ``member_family_history``
row, Anbiyam changes are recorded in ``family_anbiyam_history``, and every significant change adds a
``family_events`` entry for the family timeline.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, and_, false, or_, select, true, update
from sqlalchemy.orm import Session

from app.common.sequences import next_code
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.modules.org_units.models import OrgUnit, OrgUnitType
from app.modules.people.models import (
    Family,
    FamilyAnbiyamHistory,
    FamilyEvent,
    FamilyStatus,
    Member,
    MemberFamilyHistory,
    MemberStatus,
    OrgUnitMembership,
)
from app.modules.rbac.service import PermissionScope

ANBIYAM = "ANBIYAM"
_PUNCT = re.compile(r"[.,'\"`’()\[\]/\\_\-]+")
_SPACES = re.compile(r"\s+")


# ----------------------------------------------------------------------------- normalisation
def normalize_name(*parts: str | None) -> str:
    text = unicodedata.normalize("NFKC", " ".join(p for p in parts if p)).casefold()
    return _SPACES.sub(" ", _PUNCT.sub(" ", text)).strip()


def phone_digits(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 6 else None


def age_on(dob: date | None, on: date | None = None) -> int | None:
    if dob is None:
        return None
    on = on or date.today()
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


# ----------------------------------------------------------------------------- scoping
def family_scope(scope: PermissionScope) -> ColumnElement[bool]:
    """Anbiyam-scoped holders (e.g. Anbiyam leaders) see the families of their Anbiyam(s) only."""
    if scope.parish_wide:
        return true()
    if not scope.org_unit_ids:
        return false()
    return Family.anbiyam_id.in_(scope.org_unit_ids)


def can_access_family(scope: PermissionScope, family: Family) -> bool:
    return scope.parish_wide or (family.anbiyam_id is not None and family.anbiyam_id in scope.org_unit_ids)


def get_family(db: Session, public_id: str, scope: PermissionScope | None = None) -> Family:
    f = db.scalars(select(Family).where(Family.public_id == public_id, Family.is_deleted.is_(False))).first()
    if f is None or (scope is not None and not can_access_family(scope, f)):
        raise NotFound("Family not found")
    return f


def get_member(db: Session, public_id: str, scope: PermissionScope | None = None) -> Member:
    m = db.scalars(select(Member).where(Member.public_id == public_id, Member.is_deleted.is_(False))).first()
    if m is None or (scope is not None and not can_access_family(scope, m.family)):
        raise NotFound("Member not found")
    return m


def get_anbiyam(db: Session, public_id: str | None) -> OrgUnit | None:
    if not public_id:
        return None
    unit = db.scalars(
        select(OrgUnit)
        .join(OrgUnitType, OrgUnitType.id == OrgUnit.type_id)
        .where(OrgUnit.public_id == public_id, OrgUnit.is_deleted.is_(False), OrgUnitType.code == ANBIYAM)
    ).first()
    if unit is None:
        raise ValidationFailed(details=[{"field": "anbiyam_id", "message": "Anbiyam not found"}])
    if unit.status != "ACTIVE":
        raise ValidationFailed(details=[{"field": "anbiyam_id", "message": "This Anbiyam is not active"}])
    return unit


def event(
    db: Session,
    family: Family,
    event_type: str,
    *,
    actor: int | None,
    member: Member | None = None,
    related: Family | None = None,
    on: date | None = None,
    **details: Any,
) -> None:
    db.add(
        FamilyEvent(
            family_id=family.id,
            event_type=event_type,
            member_id=member.id if member else None,
            related_family_id=related.id if related else None,
            occurred_on=on or date.today(),
            details={k: (v.isoformat() if isinstance(v, date) else v) for k, v in details.items()},
            performed_by=actor,
        )
    )


# ----------------------------------------------------------------------------- duplicates
@dataclass
class DuplicateCandidate:
    family_id: str
    family_code: str
    family_name: str
    status: str
    reasons: list[str] = field(default_factory=list)


def find_duplicates(
    db: Session,
    *,
    family_name: str | None,
    phone: str | None,
    members: list[dict[str, Any]],
    exclude_family_id: int | None = None,
) -> list[DuplicateCandidate]:
    """Families that look like the one being registered: same phone, same family name + city/phone,
    or a member with the same normalised name and date of birth (or phone)."""
    found: dict[int, DuplicateCandidate] = {}

    def add(f: Family, reason: str) -> None:
        if exclude_family_id is not None and f.id == exclude_family_id:
            return
        c = found.setdefault(f.id, DuplicateCandidate(f.public_id, f.code, f.family_name, f.status))
        if reason not in c.reasons:
            c.reasons.append(reason)

    live = Family.is_deleted.is_(False)
    digits = phone_digits(phone)
    if digits:
        for f in db.scalars(select(Family).where(live, Family.phone_digits == digits)):
            add(f, f"Same family phone ({phone})")
    if family_name:
        for f in db.scalars(
            select(Family).where(live, Family.search_name == normalize_name(family_name)).limit(20)
        ):
            if digits and f.phone_digits == digits:
                continue
            add(f, f"Same family name ({f.family_name})")
    for m in members:
        name = normalize_name(m.get("first_name"), m.get("last_name"))
        conds = []
        if m.get("date_of_birth"):
            conds.append(and_(Member.search_name == name, Member.date_of_birth == m["date_of_birth"]))
        mdigits = phone_digits(m.get("phone"))
        if mdigits:
            conds.append(Member.phone_digits == mdigits)
        if not conds:
            continue
        stmt = select(Member).where(Member.is_deleted.is_(False), or_(*conds)).limit(20)
        for existing in db.scalars(stmt):
            why = (
                f"Member {existing.full_name} ({existing.code}) has the same name and date of birth"
                if existing.search_name == name and m.get("date_of_birth") == existing.date_of_birth
                else f"Member {existing.full_name} ({existing.code}) has the same phone"
            )
            add(existing.family, why)
    return list(found.values())


# ----------------------------------------------------------------------------- members
MEMBER_FIELDS = (
    "first_name",
    "last_name",
    "name_local",
    "gender",
    "date_of_birth",
    "relationship_to_head",
    "phone",
    "email",
    "education",
    "occupation",
    "marital_status",
    "baptism_date",
    "baptism_place",
    "baptism_register_ref",
    "communion_date",
    "communion_place",
    "confirmation_date",
    "confirmation_place",
    "marriage_date",
    "marriage_place",
    "marriage_register_ref",
    "remarks",
)


def _validate_member_data(data: dict[str, Any]) -> None:
    dob = data.get("date_of_birth")
    if dob and dob > date.today():
        raise ValidationFailed(details=[{"field": "date_of_birth", "message": "Cannot be in the future"}])
    for f in ("baptism_date", "communion_date", "confirmation_date", "marriage_date"):
        d = data.get(f)
        if d and dob and d < dob:
            raise ValidationFailed(details=[{"field": f, "message": "Cannot be before the date of birth"}])
        if d and d > date.today():
            raise ValidationFailed(details=[{"field": f, "message": "Cannot be in the future"}])


def apply_member_data(m: Member, data: dict[str, Any]) -> None:
    _validate_member_data({**{f: getattr(m, f, None) for f in ("date_of_birth",)}, **data})
    for k, v in data.items():
        if k in MEMBER_FIELDS:
            setattr(m, k, v)
    m.search_name = normalize_name(m.first_name, m.last_name)
    m.phone_digits = phone_digits(m.phone)


def add_member(
    db: Session,
    family: Family,
    data: dict[str, Any],
    *,
    actor: int | None,
    reason: str = "ADDED",
    on: date | None = None,
) -> Member:
    if family.status in (FamilyStatus.MERGED, FamilyStatus.TRANSFERRED_OUT):
        raise Conflict("Members cannot be added to a merged or transferred family", code="INVALID_STATE")
    m = Member(
        family_id=family.id, code=next_code(db, "MEMBER"), created_by=actor, status=MemberStatus.ACTIVE
    )
    apply_member_data(m, data)
    db.add(m)
    db.flush()
    db.add(
        MemberFamilyHistory(
            member_id=m.id,
            family_id=family.id,
            relationship_to_head=m.relationship_to_head,
            valid_from=on or date.today(),
            reason=reason,
            changed_by=actor,
        )
    )
    return m


def set_head(
    db: Session,
    family: Family,
    member: Member,
    *,
    actor: int | None,
    previous_head_relationship: str = "OTHER",
) -> None:
    if member.family_id != family.id or member.status != MemberStatus.ACTIVE:
        raise ValidationFailed(
            details=[{"field": "member_id", "message": "Head must be an active member of the family"}]
        )
    if family.head_member_id == member.id:
        return
    old = db.get(Member, family.head_member_id) if family.head_member_id else None
    # Demote every other member still marked HEAD: the current head, and also a former head whose
    # head_member_id link was already cleared (deceased, deactivated) – otherwise two members would be HEAD.
    for other in db.scalars(
        select(Member).where(
            Member.family_id == family.id,
            Member.id != member.id,
            Member.relationship_to_head == "HEAD",
            Member.is_deleted.is_(False),
        )
    ):
        other.relationship_to_head = previous_head_relationship
        if old is None:
            old = other
    family.head_member_id = member.id
    member.relationship_to_head = "HEAD"
    event(
        db,
        family,
        "HEAD_CHANGED",
        actor=actor,
        member=member,
        new_head=member.full_name,
        previous_head=old.full_name if old else None,
    )


# ----------------------------------------------------------------------------- families
def _set_anbiyam_history(
    db: Session, family: Family, unit: OrgUnit | None, on: date, reason: str | None, actor: int | None
) -> None:
    db.execute(
        update(FamilyAnbiyamHistory)
        .where(FamilyAnbiyamHistory.family_id == family.id, FamilyAnbiyamHistory.valid_to.is_(None))
        .values(valid_to=on)
    )
    if unit is not None:
        db.add(
            FamilyAnbiyamHistory(
                family_id=family.id, anbiyam_id=unit.id, valid_from=on, reason=reason, changed_by=actor
            )
        )


def register_family(
    db: Session,
    data: dict[str, Any],
    members: list[dict[str, Any]],
    *,
    anbiyam: OrgUnit | None,
    actor: int | None,
    registered_on: date | None = None,
) -> Family:
    heads = [m for m in members if m.get("relationship_to_head") == "HEAD"]
    if len(heads) != 1:
        raise ValidationFailed(
            "Exactly one member must be the head of the family",
            code="FAMILY_HEAD_REQUIRED",
            details=[{"field": "members", "message": "Mark exactly one member as HEAD"}],
        )
    on = registered_on or date.today()
    f = Family(
        code=next_code(db, "FAMILY"),
        registered_on=on,
        created_by=actor,
        anbiyam_id=anbiyam.id if anbiyam else None,
        status=FamilyStatus.ACTIVE if anbiyam else FamilyStatus.PENDING_ANBIYAM,
        **{k: data.get(k) for k in FAMILY_FIELDS},
    )
    f.search_name = normalize_name(f.family_name)
    f.phone_digits = phone_digits(f.phone)
    db.add(f)
    db.flush()
    created = [add_member(db, f, m, actor=actor, reason="REGISTERED", on=on) for m in members]
    head = next(m for m in created if m.relationship_to_head == "HEAD")
    f.head_member_id = head.id
    _set_anbiyam_history(db, f, anbiyam, on, "Registration", actor)
    event(
        db,
        f,
        "REGISTERED",
        actor=actor,
        on=on,
        members=len(created),
        anbiyam=anbiyam.name if anbiyam else None,
    )
    db.flush()
    return f


FAMILY_FIELDS = (
    "family_name",
    "family_name_local",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "phone",
    "email",
    "previous_parish",
    "previous_diocese",
    "remarks",
)


def update_family(f: Family, data: dict[str, Any]) -> None:
    for k, v in data.items():
        if k in FAMILY_FIELDS:
            setattr(f, k, v)
    f.search_name = normalize_name(f.family_name)
    f.phone_digits = phone_digits(f.phone)


def _require_open(f: Family) -> None:
    if f.status in (FamilyStatus.MERGED, FamilyStatus.TRANSFERRED_OUT):
        raise Conflict(f"This family is {f.status.lower().replace('_', ' ')}", code="INVALID_STATE")


def change_anbiyam(
    db: Session, f: Family, unit: OrgUnit | None, *, on: date | None, reason: str | None, actor: int | None
) -> None:
    _require_open(f)
    if (unit.id if unit else None) == f.anbiyam_id:
        raise ValidationFailed(
            details=[{"field": "anbiyam_id", "message": "The family is already in this Anbiyam"}]
        )
    on = on or date.today()
    old = db.get(OrgUnit, f.anbiyam_id) if f.anbiyam_id else None
    f.anbiyam_id = unit.id if unit else None
    if f.status in (FamilyStatus.ACTIVE, FamilyStatus.PENDING_ANBIYAM):
        f.status = FamilyStatus.ACTIVE if unit else FamilyStatus.PENDING_ANBIYAM
    _set_anbiyam_history(db, f, unit, on, reason, actor)
    event(
        db,
        f,
        "ANBIYAM_CHANGED",
        actor=actor,
        on=on,
        from_anbiyam=old.name if old else None,
        to_anbiyam=unit.name if unit else None,
        reason=reason,
    )


def end_memberships(
    db: Session,
    *,
    member_ids: list[int] | None = None,
    family_ids: list[int] | None = None,
    on: date,
    reason: str,
) -> int:
    conds = []
    if member_ids:
        conds.append(OrgUnitMembership.member_id.in_(member_ids))
    if family_ids:
        conds.append(OrgUnitMembership.family_id.in_(family_ids))
    if not conds:
        return 0
    res = db.execute(
        update(OrgUnitMembership)
        .where(OrgUnitMembership.left_on.is_(None), or_(*conds))
        .values(left_on=on, end_reason=reason)
    )
    return res.rowcount or 0


def set_family_status(db: Session, f: Family, active: bool, *, reason: str | None, actor: int | None) -> None:
    _require_open(f)
    new = (
        (FamilyStatus.ACTIVE if f.anbiyam_id else FamilyStatus.PENDING_ANBIYAM)
        if active
        else FamilyStatus.INACTIVE
    )
    if new == f.status:
        return
    old = f.status
    f.status = new
    event(db, f, "STATUS_CHANGED", actor=actor, from_status=old, to_status=new, reason=reason)


def transfer_out(
    db: Session,
    f: Family,
    *,
    to_parish: str,
    to_diocese: str | None,
    on: date | None,
    reason: str | None,
    actor: int | None,
) -> None:
    _require_open(f)
    on = on or date.today()
    active = [m for m in f.members if m.status == MemberStatus.ACTIVE]
    for m in active:
        m.status = MemberStatus.TRANSFERRED_OUT
    end_memberships(
        db, member_ids=[m.id for m in active], family_ids=[f.id], on=on, reason="Family transferred out"
    )
    _set_anbiyam_history(db, f, None, on, "Transferred out", actor)
    f.status = FamilyStatus.TRANSFERRED_OUT
    event(
        db,
        f,
        "TRANSFERRED_OUT",
        actor=actor,
        on=on,
        to_parish=to_parish,
        to_diocese=to_diocese,
        reason=reason,
        members=len(active),
    )


def _move(
    db: Session, m: Member, target: Family, *, relationship: str, reason: str, on: date, actor: int | None
) -> None:
    db.execute(
        update(MemberFamilyHistory)
        .where(MemberFamilyHistory.member_id == m.id, MemberFamilyHistory.valid_to.is_(None))
        .values(valid_to=on)
    )
    old = m.family
    if old.head_member_id == m.id:
        old.head_member_id = None
    m.family_id = target.id
    m.relationship_to_head = relationship
    db.add(
        MemberFamilyHistory(
            member_id=m.id,
            family_id=target.id,
            relationship_to_head=relationship,
            valid_from=on,
            reason=reason,
            changed_by=actor,
        )
    )
    db.flush()
    db.expire(m, ["family"])


def move_member(
    db: Session,
    m: Member,
    target: Family,
    *,
    relationship: str,
    on: date | None,
    reason: str | None,
    actor: int | None,
    new_head_for_old_family: Member | None = None,
) -> None:
    if m.family_id == target.id:
        raise ValidationFailed(details=[{"field": "family_id", "message": "Already in this family"}])
    _require_open(target)
    if m.status != MemberStatus.ACTIVE:
        raise Conflict("Only active members can be moved", code="INVALID_STATE")
    old = m.family
    on = on or date.today()
    was_head = old.head_member_id == m.id
    remaining = [x for x in old.members if x.id != m.id and x.status == MemberStatus.ACTIVE]
    if was_head and remaining and new_head_for_old_family is None:
        raise ValidationFailed(
            "Choose a new head for the family the member leaves",
            code="FAMILY_HEAD_REQUIRED",
            details=[{"field": "new_head_member_id", "message": "Required"}],
        )
    if relationship == "HEAD" and target.head_member_id is not None:
        raise ValidationFailed(
            details=[{"field": "relationship_to_head", "message": "The family already has a head"}]
        )
    _move(db, m, target, relationship=relationship, reason="MOVED", on=on, actor=actor)
    if relationship == "HEAD":
        target.head_member_id = m.id
    if was_head and new_head_for_old_family is not None:
        set_head(db, old, new_head_for_old_family, actor=actor)
    event(db, old, "MEMBER_MOVED_OUT", actor=actor, member=m, related=target, on=on, reason=reason)
    event(db, target, "MEMBER_MOVED_IN", actor=actor, member=m, related=old, on=on, reason=reason)


def merge_families(
    db: Session, source: Family, target: Family, *, on: date | None, reason: str | None, actor: int | None
) -> int:
    if source.id == target.id:
        raise ValidationFailed(
            details=[{"field": "into_family_id", "message": "Cannot merge a family into itself"}]
        )
    _require_open(source)
    _require_open(target)
    on = on or date.today()
    moved = 0
    for m in [x for x in source.members if x.status == MemberStatus.ACTIVE]:
        rel = "OTHER_RELATIVE" if m.relationship_to_head == "HEAD" else m.relationship_to_head
        _move(db, m, target, relationship=rel, reason="MERGE", on=on, actor=actor)
        moved += 1
    # Inactive/deceased members follow too, so the history stays with the surviving family.
    for m in [x for x in source.members if x.status != MemberStatus.ACTIVE]:
        _move(db, m, target, relationship=m.relationship_to_head, reason="MERGE", on=on, actor=actor)
    end_memberships(db, family_ids=[source.id], on=on, reason="Family merged")
    _set_anbiyam_history(db, source, None, on, "Merged", actor)
    source.status = FamilyStatus.MERGED
    source.merged_into_id = target.id
    source.head_member_id = None
    event(db, source, "MERGED_INTO", actor=actor, related=target, on=on, reason=reason, members=moved)
    event(db, target, "MERGED_FROM", actor=actor, related=source, on=on, reason=reason, members=moved)
    return moved


def split_family(
    db: Session,
    f: Family,
    *,
    member_ids: list[str],
    new_family: dict[str, Any],
    head_member_id: str,
    remaining_head_member_id: str | None,
    anbiyam: OrgUnit | None,
    on: date | None,
    reason: str | None,
    actor: int | None,
) -> Family:
    _require_open(f)
    on = on or date.today()
    by_id = {m.public_id: m for m in f.members if m.status == MemberStatus.ACTIVE}
    unknown = set(member_ids) - set(by_id)
    if unknown or not member_ids:
        raise ValidationFailed(
            details=[{"field": "member_ids", "message": "Choose active members of this family"}]
        )
    if head_member_id not in member_ids:
        raise ValidationFailed(
            details=[{"field": "head_member_id", "message": "The new head must be one of the moving members"}]
        )
    remaining = [m for pid, m in by_id.items() if pid not in member_ids]
    old_head_moves = f.head_member_id is not None and any(by_id[p].id == f.head_member_id for p in member_ids)
    remaining_head = None
    if old_head_moves and remaining:
        if remaining_head_member_id not in {m.public_id for m in remaining}:
            raise ValidationFailed(
                "Choose a new head for the remaining family",
                code="FAMILY_HEAD_REQUIRED",
                details=[{"field": "remaining_head_member_id", "message": "Required"}],
            )
        remaining_head = next(m for m in remaining if m.public_id == remaining_head_member_id)
    data = {k: new_family.get(k, getattr(f, k)) for k in FAMILY_FIELDS if k not in ("remarks",)}
    data["remarks"] = new_family.get("remarks")
    nf = Family(
        code=next_code(db, "FAMILY"),
        registered_on=on,
        created_by=actor,
        anbiyam_id=anbiyam.id if anbiyam else None,
        status=FamilyStatus.ACTIVE if anbiyam else FamilyStatus.PENDING_ANBIYAM,
        **data,
    )
    nf.search_name = normalize_name(nf.family_name)
    nf.phone_digits = phone_digits(nf.phone)
    db.add(nf)
    db.flush()
    for pid in member_ids:
        m = by_id[pid]
        _move(
            db,
            m,
            nf,
            relationship="HEAD" if pid == head_member_id else m.relationship_to_head,
            reason="SPLIT",
            on=on,
            actor=actor,
        )
    nf.head_member_id = by_id[head_member_id].id
    if remaining_head is not None:
        set_head(db, f, remaining_head, actor=actor)
    if not remaining:
        f.status = FamilyStatus.INACTIVE
    _set_anbiyam_history(db, nf, anbiyam, on, "Split from " + f.code, actor)
    event(db, f, "SPLIT", actor=actor, related=nf, on=on, reason=reason, members=len(member_ids))
    event(db, nf, "SPLIT_FROM", actor=actor, related=f, on=on, reason=reason, members=len(member_ids))
    db.flush()
    return nf


def mark_deceased(
    db: Session, m: Member, *, date_of_death: date, remarks: str | None, actor: int | None
) -> None:
    if m.status == MemberStatus.DECEASED:
        raise Conflict("Already recorded as deceased", code="INVALID_STATE")
    if date_of_death > date.today() or (m.date_of_birth and date_of_death < m.date_of_birth):
        raise ValidationFailed(details=[{"field": "date_of_death", "message": "Invalid date"}])
    m.status = MemberStatus.DECEASED
    m.date_of_death = date_of_death
    end_memberships(db, member_ids=[m.id], on=date_of_death, reason="Deceased")
    f = m.family
    was_head = f.head_member_id == m.id
    if was_head:
        f.head_member_id = None
    event(
        db,
        f,
        "MEMBER_DECEASED",
        actor=actor,
        member=m,
        on=date_of_death,
        member_name=m.full_name,
        was_head=was_head,
        remarks=remarks,
    )


def set_member_status(db: Session, m: Member, active: bool, *, reason: str | None, actor: int | None) -> None:
    if m.status == MemberStatus.DECEASED:
        raise Conflict("A deceased member's status cannot be changed", code="INVALID_STATE")
    new = MemberStatus.ACTIVE if active else MemberStatus.INACTIVE
    if m.status == new:
        return
    if active:
        _require_open(m.family)
    else:
        end_memberships(db, member_ids=[m.id], on=date.today(), reason=reason or "Inactive")
        if m.family.head_member_id == m.id:
            m.family.head_member_id = None
    old = m.status
    m.status = new
    event(
        db,
        m.family,
        "MEMBER_STATUS_CHANGED",
        actor=actor,
        member=m,
        member_name=m.full_name,
        from_status=old,
        to_status=new,
        reason=reason,
    )


# ----------------------------------------------------------------------------- organisation memberships
def join(
    db: Session,
    unit: OrgUnit,
    *,
    member: Member | None,
    family: Family | None,
    joined_on: date | None,
    remarks: str | None,
    actor: int | None,
) -> OrgUnitMembership:
    t = unit.type
    if unit.status != "ACTIVE":
        raise Conflict("This organisation is not active", code="INVALID_STATE")
    if t.code == ANBIYAM:
        raise ValidationFailed(
            "Families join an Anbiyam from the family record (Change Anbiyam)", code="USE_FAMILY_ANBIYAM"
        )
    if t.member_kind == "FAMILY":
        if family is None or member is not None:
            raise ValidationFailed(
                details=[{"field": "family_id", "message": f"Families join {t.name_plural}"}]
            )
        _require_open(family)
    else:
        if member is None or family is not None:
            raise ValidationFailed(
                details=[{"field": "member_id", "message": f"Members join {t.name_plural}"}]
            )
        if member.status != MemberStatus.ACTIVE:
            raise Conflict("Only active members can join", code="INVALID_STATE")
        rules = t.membership_rules or {}
        age = age_on(member.date_of_birth)
        problems = []
        if (rules.get("min_age") is not None or rules.get("max_age") is not None) and age is None:
            problems.append("Date of birth is required for this organisation's age rule")
        if age is not None and rules.get("min_age") is not None and age < rules["min_age"]:
            problems.append(f"Minimum age is {rules['min_age']}")
        if age is not None and rules.get("max_age") is not None and age > rules["max_age"]:
            problems.append(f"Maximum age is {rules['max_age']}")
        if rules.get("genders") and member.gender not in rules["genders"]:
            problems.append(f"Open to: {', '.join(rules['genders'])}")
        limit = rules.get("max_units_per_member")
        if limit:
            n = len(
                db.scalars(
                    select(OrgUnitMembership.id)
                    .join(OrgUnit, OrgUnit.id == OrgUnitMembership.org_unit_id)
                    .where(
                        OrgUnitMembership.member_id == member.id,
                        OrgUnitMembership.left_on.is_(None),
                        OrgUnit.type_id == t.id,
                    )
                ).all()
            )
            if n >= limit:
                problems.append(f"A member may belong to at most {limit} {t.name_plural.lower()}")
        if problems:
            raise ValidationFailed(
                "Membership rules not met",
                code="MEMBERSHIP_RULES",
                details=[{"field": "member_id", "message": p} for p in problems],
            )
    dup = db.scalars(
        select(OrgUnitMembership.id).where(
            OrgUnitMembership.org_unit_id == unit.id,
            OrgUnitMembership.left_on.is_(None),
            OrgUnitMembership.member_id == member.id if member else OrgUnitMembership.family_id == family.id,  # type: ignore[union-attr]
        )
    ).first()
    if dup is not None:
        raise Conflict("Already a member of this organisation", code="ALREADY_MEMBER")
    ms = OrgUnitMembership(
        org_unit_id=unit.id,
        member_id=member.id if member else None,
        family_id=family.id if family else None,
        joined_on=joined_on or date.today(),
        remarks=remarks,
        created_by=actor,
    )
    db.add(ms)
    db.flush()
    return ms

"""Family & member register APIs (``/api/v1/families``, ``/api/v1/members``) and organisation memberships.

Authorization: ``family.*`` / ``member.*`` permissions. Anbiyam-scoped holders (Anbiyam leaders) work
on the families of their Anbiyam(s) only; everything else is parish-wide. Out-of-scope records are
reported as 404. Sensitive member fields need ``member.view_sensitive``; sacramental fields need
``sacrament.view`` (read) and ``sacrament.update`` (write).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import changes, record_audit
from app.common.exports import Column, ExportFormat, export_table
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.core.errors import AppError, NotFound, PermissionDenied, ValidationFailed
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.org_units.models import OrgUnit
from app.modules.people import service as svc
from app.modules.people.models import (
    Family,
    FamilyAnbiyamHistory,
    FamilyEvent,
    FamilyStatus,
    Member,
    MemberStatus,
    OrgUnitMembership,
)
from app.modules.people.schemas import (
    SACRAMENT_FIELDS,
    SENSITIVE_FIELDS,
    AnbiyamHistoryOut,
    ChangeAnbiyamIn,
    DeceasedIn,
    DuplicateCheckIn,
    DuplicateOut,
    FamilyCreate,
    FamilyEventOut,
    FamilyHistoryOut,
    FamilyListOut,
    FamilyOut,
    FamilyUpdate,
    MemberIn,
    MemberOut,
    MembershipEndIn,
    MembershipIn,
    MembershipOut,
    MemberUpdate,
    MergeIn,
    MoveMemberIn,
    Ref,
    SetHeadIn,
    SplitIn,
    StatusIn,
    TransferOutIn,
)
from app.modules.rbac.deps import require_perm
from app.modules.rbac.service import PermissionScope
from app.tenancy.deps import TenantSession

families = APIRouter(prefix="/families", tags=["families"])
members = APIRouter(prefix="/members", tags=["members"])
memberships = APIRouter(prefix="/org-units", tags=["organisations"])
MODULE = "people"


def _p(code: str):  # type: ignore[no-untyped-def]
    return Annotated[PermissionScope, Depends(require_perm(code))]


FamilyView, FamilyCreateP, FamilyUpdateP = _p("family.view"), _p("family.create"), _p("family.update")
FamilyTransfer, FamilyExport = _p("family.transfer"), _p("family.export")
MemberView, MemberCreate, MemberUpdateP = _p("member.view"), _p("member.create"), _p("member.update")
MemberDelete, MemberExport = _p("member.delete"), _p("member.export")
OrgView, OrgManage = _p("org_unit.view"), _p("org_unit.manage_members")


class DuplicateSuspected(AppError):
    status_code = 409
    code = "DUPLICATE_SUSPECTED"
    message = "Similar families are already registered"


# ============================================================================ serialisers
def _ref_family(f: Family) -> Ref:
    return Ref(id=f.public_id, code=f.code, name=f.family_name)


def _ref_unit(u: OrgUnit | None) -> Ref | None:
    return Ref(id=u.public_id, code=u.code, name=u.name) if u else None


def _units(db: Session, ids: set[int | None]) -> dict[int, OrgUnit]:
    real = {i for i in ids if i}
    return {u.id: u for u in db.scalars(select(OrgUnit).where(OrgUnit.id.in_(real)))} if real else {}


def member_out(m: Member, auth: Auth, units: dict[int, OrgUnit]) -> MemberOut:
    f = m.family
    unit_id = f.anbiyam_id
    sens = auth.permissions.has("member.view_sensitive", unit_id) or auth.permissions.has(
        "member.view_sensitive"
    )
    sac = auth.permissions.has("sacrament.view", unit_id) or auth.permissions.has("sacrament.view")
    data: dict[str, Any] = dict(
        id=m.public_id,
        code=m.code,
        family=_ref_family(f),
        anbiyam=_ref_unit(units.get(unit_id) if unit_id else None),
        first_name=m.first_name,
        last_name=m.last_name,
        full_name=m.full_name,
        name_local=m.name_local,
        gender=m.gender,
        age=svc.age_on(m.date_of_birth, m.date_of_death),
        relationship_to_head=m.relationship_to_head,
        is_head=f.head_member_id == m.id,
        status=m.status,
        date_of_death=m.date_of_death,
        sensitive_visible=sens,
        sacraments_visible=sac,
        created_at=m.created_at,
    )
    if sens:
        data.update({k: getattr(m, k) for k in SENSITIVE_FIELDS})
    if sac:
        data.update({k: getattr(m, k) for k in SACRAMENT_FIELDS})
    return MemberOut(**data)


def _member_counts(db: Session, family_ids: list[int]) -> dict[int, int]:
    if not family_ids:
        return {}
    rows = db.execute(
        select(Member.family_id, func.count())
        .where(
            Member.family_id.in_(family_ids),
            Member.status == MemberStatus.ACTIVE,
            Member.is_deleted.is_(False),
        )
        .group_by(Member.family_id)
    )
    return dict(rows.all())  # type: ignore[arg-type]


def _family_list_out(
    f: Family, units: dict[int, OrgUnit], counts: dict[int, int], heads: dict[int, Member]
) -> FamilyListOut:
    head = heads.get(f.head_member_id) if f.head_member_id else None
    return FamilyListOut(
        id=f.public_id,
        code=f.code,
        family_name=f.family_name,
        family_name_local=f.family_name_local,
        head_name=head.full_name if head else None,
        anbiyam=_ref_unit(units.get(f.anbiyam_id) if f.anbiyam_id else None),
        member_count=counts.get(f.id, 0),
        phone=f.phone,
        city=f.city,
        status=f.status,
        registered_on=f.registered_on,
    )


def family_out(db: Session, f: Family, auth: Auth) -> FamilyOut:
    db.flush()  # persist pending changes first: refresh() would otherwise discard them
    db.refresh(f)
    units = _units(db, {f.anbiyam_id})
    mems = sorted(f.members, key=lambda m: (m.status != MemberStatus.ACTIVE, m.id != f.head_member_id, m.id))
    heads = {m.id: m for m in mems}
    base = _family_list_out(f, units, {f.id: sum(1 for m in mems if m.status == MemberStatus.ACTIVE)}, heads)
    merged = db.get(Family, f.merged_into_id) if f.merged_into_id else None
    return FamilyOut(
        **base.model_dump(),
        address_line1=f.address_line1,
        address_line2=f.address_line2,
        state=f.state,
        postal_code=f.postal_code,
        email=f.email,
        previous_parish=f.previous_parish,
        previous_diocese=f.previous_diocese,
        remarks=f.remarks,
        merged_into=_ref_family(merged) if merged else None,
        head_member_id=heads[f.head_member_id].public_id if f.head_member_id in heads else None,
        members=[member_out(m, auth, units) for m in mems],
        created_at=f.created_at,
    )


def _check_sacrament_write(auth: Auth, data: dict[str, Any], unit_id: int | None) -> None:
    if any(k in data and data[k] is not None for k in SACRAMENT_FIELDS) and not (
        auth.permissions.has("sacrament.update", unit_id) or auth.permissions.has("sacrament.update")
    ):
        raise PermissionDenied(
            "Recording sacraments requires the sacrament.update permission",
            details=[{"field": "permission", "message": "sacrament.update"}],
        )


def _check_sensitive_write(auth: Auth, data: dict[str, Any], unit_id: int | None) -> None:
    if any(k in data for k in SENSITIVE_FIELDS) and not (
        auth.permissions.has("member.view_sensitive", unit_id)
        or auth.permissions.has("member.view_sensitive")
    ):
        raise PermissionDenied(
            "Editing personal details requires member.view_sensitive",
            details=[{"field": "permission", "message": "member.view_sensitive"}],
        )


def _require(auth: Auth, code: str, family: Family) -> None:
    if not auth.permissions.has(code, family.anbiyam_id):
        raise PermissionDenied(details=[{"field": "permission", "message": code}])


def _audit(
    db: Session, auth: Auth, request: Request, action: str, entity: str, entity_id: str, **kw: Any
) -> None:
    record_audit(
        db,
        action=action,
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type=entity,
        entity_id=entity_id,
        **kw,
    )


# ============================================================================ families
def _family_query(
    db: Session,
    scope: PermissionScope,
    q: str | None,
    anbiyam: str | None,
    status_: str | None,
    registered_from: date | None,
    registered_to: date | None,
) -> Select[Any]:
    stmt = select(Family).where(Family.is_deleted.is_(False), svc.family_scope(scope))
    if q:
        term = q.strip()
        like = f"%{term}%"
        name = f"%{svc.normalize_name(term)}%"
        digits = svc.phone_digits(term)
        conds = [
            Family.code.ilike(like),
            Family.search_name.like(name),
            Family.family_name_local.ilike(like),
            exists().where(
                Member.family_id == Family.id,
                Member.is_deleted.is_(False),
                or_(Member.search_name.like(name), Member.name_local.ilike(like), Member.code.ilike(like)),
            ),
        ]
        if digits:
            conds.append(Family.phone_digits.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    if anbiyam == "none":
        stmt = stmt.where(Family.anbiyam_id.is_(None))
    elif anbiyam:
        unit = db.scalars(select(OrgUnit).where(OrgUnit.public_id == anbiyam)).first()
        stmt = stmt.where(Family.anbiyam_id == (unit.id if unit else -1))
    if status_:
        stmt = stmt.where(Family.status == status_)
    if registered_from:
        stmt = stmt.where(Family.registered_on >= registered_from)
    if registered_to:
        stmt = stmt.where(Family.registered_on <= registered_to)
    return stmt


@families.get("", response_model=Page[FamilyListOut])
def list_families(
    scope: FamilyView,
    db: TenantSession,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100, description="Code, family/member name, phone")] = None,
    anbiyam: Annotated[str | None, Query(description="Anbiyam public id, or 'none'")] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    registered_from: date | None = None,
    registered_to: date | None = None,
) -> Page[FamilyListOut]:
    stmt = _family_query(db, scope, q, anbiyam, status_, registered_from, registered_to)
    stmt = apply_sort(
        stmt,
        params.sort,
        {"code": Family.code, "family_name": Family.family_name, "registered_on": Family.registered_on},
        [Family.family_name, Family.id],
    )
    page = paginate(db, stmt, params, lambda f: f)
    units = _units(db, {f.anbiyam_id for f in page.items})
    counts = _member_counts(db, [f.id for f in page.items])
    head_ids = {f.head_member_id for f in page.items if f.head_member_id}
    heads = {m.id: m for m in db.scalars(select(Member).where(Member.id.in_(head_ids)))} if head_ids else {}
    return Page[FamilyListOut](
        items=[_family_list_out(f, units, counts, heads) for f in page.items],
        page=page.page,
        size=page.size,
        total=page.total,
        pages=page.pages,
    )


@families.post("/check-duplicates", response_model=list[DuplicateOut])
def check_duplicates(body: DuplicateCheckIn, _: FamilyCreateP, db: TenantSession) -> list[DuplicateOut]:
    found = svc.find_duplicates(
        db, family_name=body.family_name, phone=body.phone, members=[m.model_dump() for m in body.members]
    )
    return [DuplicateOut(**c.__dict__) for c in found]


@families.post("", response_model=FamilyOut, status_code=status.HTTP_201_CREATED)
def register_family(
    body: FamilyCreate, request: Request, auth: Auth, scope: FamilyCreateP, db: TenantSession
) -> FamilyOut:
    anbiyam = svc.get_anbiyam(db, body.anbiyam_id)
    if not scope.allows(anbiyam.id if anbiyam else None):
        raise PermissionDenied("You may register families only in your own Anbiyam")
    members_data = [m.model_dump() for m in body.members]
    for m in members_data:
        _check_sacrament_write(auth, m, anbiyam.id if anbiyam else None)
    if not body.confirm_not_duplicate:
        found = svc.find_duplicates(db, family_name=body.family_name, phone=body.phone, members=members_data)
        if found:
            raise DuplicateSuspected(
                details=[
                    {
                        "field": c.family_id,
                        "message": f"{c.family_code} {c.family_name}: " + "; ".join(c.reasons),
                    }
                    for c in found
                ]
            )
    f = svc.register_family(
        db,
        body.model_dump(exclude={"members", "anbiyam_id", "confirm_not_duplicate"}),
        members_data,
        anbiyam=anbiyam,
        actor=auth.user.id,
        registered_on=body.registered_on,
    )
    _audit(
        db,
        auth,
        request,
        "CREATE",
        "family",
        f.public_id,
        new={
            "code": f.code,
            "family_name": f.family_name,
            "members": len(members_data),
            "duplicate_override": body.confirm_not_duplicate,
        },
    )
    return family_out(db, f, auth)


@families.get("/export")
def export_families(
    auth: Auth,
    scope: FamilyExport,
    db: TenantSession,
    request: Request,
    q: Annotated[str | None, Query(max_length=100)] = None,
    anbiyam: str | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    view_scope = auth.permissions.scope("family.view")
    stmt = _family_query(db, view_scope, q, anbiyam, status_, None, None).order_by(Family.code)
    fams = list(db.scalars(stmt))
    fams = [f for f in fams if scope.allows(f.anbiyam_id)]
    units = _units(db, {f.anbiyam_id for f in fams})
    counts = _member_counts(db, [f.id for f in fams])
    heads = {
        m.id: m for m in db.scalars(select(Member).where(Member.id.in_({f.head_member_id for f in fams})))
    }
    rows = [
        {
            **_family_list_out(f, units, counts, heads).model_dump(),
            "anbiyam_name": units[f.anbiyam_id].name if f.anbiyam_id in units else "",
            "address": ", ".join(p for p in (f.address_line1, f.address_line2, f.city, f.postal_code) if p),
        }
        for f in fams
    ]
    _audit(
        db, auth, request, "EXPORT", "family", "register", remarks=f"{len(rows)} families as {format.value}"
    )
    cols = [
        Column("code", "Family ID", 12),
        Column("family_name", "Family"),
        Column("head_name", "Head"),
        Column("anbiyam_name", "Anbiyam"),
        Column("member_count", "Members", numeric=True),
        Column("phone", "Phone"),
        Column("address", "Address", 40),
        Column("status", "Status"),
        Column("registered_on", "Registered"),
    ]
    return export_table(
        rows,
        cols,
        format,
        title="Family register",
        filename="family-register",
        parish_name=auth.tenant.name,
        generated_by=auth.user.full_name,
    )


@families.get("/{family_id}", response_model=FamilyOut)
def get_family(family_id: str, auth: Auth, scope: FamilyView, db: TenantSession) -> FamilyOut:
    return family_out(db, svc.get_family(db, family_id, scope), auth)


@families.patch("/{family_id}", response_model=FamilyOut)
def update_family(
    family_id: str, body: FamilyUpdate, request: Request, auth: Auth, scope: FamilyUpdateP, db: TenantSession
) -> FamilyOut:
    f = svc.get_family(db, family_id, scope)
    svc.update_family(f, body.model_dump(exclude_unset=True, mode="json"))
    old, new = changes(f, exclude={"search_name", "phone_digits"})
    f.updated_by = auth.user.id
    _audit(db, auth, request, "UPDATE", "family", f.public_id, old=old, new=new)
    return family_out(db, f, auth)


@families.post("/{family_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    family_id: str, body: MemberIn, request: Request, auth: Auth, _: MemberCreate, db: TenantSession
) -> MemberOut:
    f = svc.get_family(db, family_id, auth.permissions.scope("family.view"))
    _require(auth, "member.create", f)
    data = body.model_dump()
    _check_sacrament_write(auth, data, f.anbiyam_id)
    if data["relationship_to_head"] == "HEAD" and f.head_member_id is not None:
        raise ValidationFailed(
            details=[{"field": "relationship_to_head", "message": "The family already has a head"}]
        )
    m = svc.add_member(db, f, data, actor=auth.user.id)
    if data["relationship_to_head"] == "HEAD":
        f.head_member_id = m.id
    svc.event(db, f, "MEMBER_ADDED", actor=auth.user.id, member=m, member_name=m.full_name)
    _audit(
        db,
        auth,
        request,
        "CREATE",
        "member",
        m.public_id,
        new={"code": m.code, "family": f.code, "name": m.full_name},
    )
    return member_out(m, auth, _units(db, {f.anbiyam_id}))


@families.post("/{family_id}/anbiyam", response_model=FamilyOut)
def change_anbiyam(
    family_id: str,
    body: ChangeAnbiyamIn,
    request: Request,
    auth: Auth,
    scope: FamilyTransfer,
    db: TenantSession,
) -> FamilyOut:
    f = svc.get_family(db, family_id, auth.permissions.scope("family.view"))
    unit = svc.get_anbiyam(db, body.anbiyam_id)
    if not (scope.allows(f.anbiyam_id) and scope.allows(unit.id if unit else None)):
        raise PermissionDenied("Changing Anbiyam needs the transfer permission for both Anbiyams")
    svc.change_anbiyam(db, f, unit, on=body.effective_date, reason=body.reason, actor=auth.user.id)
    _audit(db, auth, request, "ANBIYAM_CHANGED", "family", f.public_id, new=body.model_dump(mode="json"))
    return family_out(db, f, auth)


@families.post("/{family_id}/head", response_model=FamilyOut)
def set_head(
    family_id: str, body: SetHeadIn, request: Request, auth: Auth, _: FamilyUpdateP, db: TenantSession
) -> FamilyOut:
    f = svc.get_family(db, family_id, auth.permissions.scope("family.view"))
    _require(auth, "family.update", f)
    m = svc.get_member(db, body.member_id)
    svc.set_head(db, f, m, actor=auth.user.id, previous_head_relationship=body.previous_head_relationship)
    _audit(db, auth, request, "HEAD_CHANGED", "family", f.public_id, new={"head": m.public_id})
    return family_out(db, f, auth)


@families.post("/{family_id}/status", response_model=FamilyOut)
def family_status(
    family_id: str, body: StatusIn, request: Request, auth: Auth, _: FamilyUpdateP, db: TenantSession
) -> FamilyOut:
    f = svc.get_family(db, family_id, auth.permissions.scope("family.view"))
    _require(auth, "family.update", f)
    svc.set_family_status(db, f, body.active, reason=body.reason, actor=auth.user.id)
    _audit(db, auth, request, "STATUS_CHANGED", "family", f.public_id, new=body.model_dump())
    return family_out(db, f, auth)


@families.post("/{family_id}/transfer-out", response_model=FamilyOut)
def transfer_out(
    family_id: str,
    body: TransferOutIn,
    request: Request,
    auth: Auth,
    scope: FamilyTransfer,
    db: TenantSession,
) -> FamilyOut:
    f = svc.get_family(db, family_id, scope)
    svc.transfer_out(
        db,
        f,
        to_parish=body.to_parish,
        to_diocese=body.to_diocese,
        on=body.effective_date,
        reason=body.reason,
        actor=auth.user.id,
    )
    _audit(db, auth, request, "TRANSFERRED_OUT", "family", f.public_id, new=body.model_dump(mode="json"))
    return family_out(db, f, auth)


@families.post("/{family_id}/merge", response_model=FamilyOut)
def merge(
    family_id: str, body: MergeIn, request: Request, auth: Auth, scope: FamilyTransfer, db: TenantSession
) -> FamilyOut:
    """Merge this family into another (e.g. a duplicate registration). Returns the surviving family."""
    src = svc.get_family(db, family_id, scope)
    target = svc.get_family(db, body.into_family_id, scope)
    n = svc.merge_families(db, src, target, on=body.effective_date, reason=body.reason, actor=auth.user.id)
    _audit(
        db,
        auth,
        request,
        "MERGED",
        "family",
        src.public_id,
        new={"into": target.public_id, "members_moved": n, "reason": body.reason},
    )
    return family_out(db, target, auth)


@families.post("/{family_id}/split", response_model=FamilyOut, status_code=status.HTTP_201_CREATED)
def split(
    family_id: str, body: SplitIn, request: Request, auth: Auth, scope: FamilyTransfer, db: TenantSession
) -> FamilyOut:
    """Move some members into a new family (e.g. a married son setting up his own household)."""
    f = svc.get_family(db, family_id, scope)
    anbiyam = (
        svc.get_anbiyam(db, body.anbiyam_id)
        if body.anbiyam_id
        else (db.get(OrgUnit, f.anbiyam_id) if f.anbiyam_id else None)
    )
    if not scope.allows(anbiyam.id if anbiyam else None):
        raise PermissionDenied("You may not place the new family in that Anbiyam")
    nf = svc.split_family(
        db,
        f,
        member_ids=body.member_ids,
        head_member_id=body.head_member_id,
        remaining_head_member_id=body.remaining_head_member_id,
        new_family=body.new_family.model_dump(exclude_unset=True, mode="json"),
        anbiyam=anbiyam,
        on=body.effective_date,
        reason=body.reason,
        actor=auth.user.id,
    )
    _audit(
        db,
        auth,
        request,
        "SPLIT",
        "family",
        f.public_id,
        new={"new_family": nf.public_id, "code": nf.code, "members": body.member_ids},
    )
    return family_out(db, nf, auth)


@families.get("/{family_id}/history", response_model=FamilyHistoryOut)
def family_history(family_id: str, scope: FamilyView, db: TenantSession) -> FamilyHistoryOut:
    f = svc.get_family(db, family_id, scope)
    evs = list(
        db.scalars(
            select(FamilyEvent)
            .where(FamilyEvent.family_id == f.id)
            .order_by(FamilyEvent.occurred_on.desc(), FamilyEvent.id.desc())
        )
    )
    mids = {e.member_id for e in evs if e.member_id}
    fids = {e.related_family_id for e in evs if e.related_family_id}
    uids = {e.performed_by for e in evs if e.performed_by}
    ms = {m.id: m for m in db.scalars(select(Member).where(Member.id.in_(mids)))} if mids else {}
    fs = {x.id: x for x in db.scalars(select(Family).where(Family.id.in_(fids)))} if fids else {}
    us = {u.id: u for u in db.scalars(select(User).where(User.id.in_(uids)))} if uids else {}
    hist = list(
        db.scalars(
            select(FamilyAnbiyamHistory)
            .where(FamilyAnbiyamHistory.family_id == f.id)
            .order_by(FamilyAnbiyamHistory.valid_from.desc(), FamilyAnbiyamHistory.id.desc())
        )
    )
    units = _units(db, {h.anbiyam_id for h in hist})
    return FamilyHistoryOut(
        events=[
            FamilyEventOut(
                event_type=e.event_type,
                occurred_on=e.occurred_on,
                created_at=e.created_at,
                details=e.details,
                member=Ref(
                    id=ms[e.member_id].public_id, code=ms[e.member_id].code, name=ms[e.member_id].full_name
                )
                if e.member_id in ms
                else None,
                related_family=_ref_family(fs[e.related_family_id]) if e.related_family_id in fs else None,
                performed_by=us[e.performed_by].full_name if e.performed_by in us else None,
            )
            for e in evs
        ],
        anbiyam_history=[
            AnbiyamHistoryOut(
                anbiyam=_ref_unit(units[h.anbiyam_id]),
                valid_from=h.valid_from,  # type: ignore[arg-type]
                valid_to=h.valid_to,
                reason=h.reason,
            )
            for h in hist
        ],
    )


# ============================================================================ members
def _member_query(
    db: Session,
    scope: PermissionScope,
    q: str | None,
    gender: str | None,
    status_: str | None,
    anbiyam: str | None,
    age_min: int | None,
    age_max: int | None,
) -> Select[Any]:
    stmt = (
        select(Member)
        .join(Family, Family.id == Member.family_id)
        .where(Member.is_deleted.is_(False), Family.is_deleted.is_(False), svc.family_scope(scope))
    )
    if q:
        like = f"%{q.strip()}%"
        name = f"%{svc.normalize_name(q)}%"
        digits = svc.phone_digits(q)
        conds = [
            Member.code.ilike(like),
            Member.search_name.like(name),
            Member.name_local.ilike(like),
            Family.code.ilike(like),
        ]
        if digits:
            conds.append(Member.phone_digits.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    if gender:
        stmt = stmt.where(Member.gender == gender)
    if status_:
        stmt = stmt.where(Member.status == status_)
    if anbiyam:
        unit = db.scalars(select(OrgUnit).where(OrgUnit.public_id == anbiyam)).first()
        stmt = stmt.where(Family.anbiyam_id == (unit.id if unit else -1))
    today = date.today()
    if age_min is not None:
        stmt = stmt.where(Member.date_of_birth <= today.replace(year=today.year - age_min))
    if age_max is not None:
        stmt = stmt.where(Member.date_of_birth > today.replace(year=today.year - age_max - 1))
    return stmt


@members.get("", response_model=Page[MemberOut])
def list_members(
    auth: Auth,
    scope: MemberView,
    db: TenantSession,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    gender: Annotated[str | None, Query(pattern=r"^[MFO]$")] = None,
    status_: Annotated[str | None, Query(alias="status")] = "ACTIVE",
    anbiyam: str | None = None,
    age_min: Annotated[int | None, Query(ge=0, le=120)] = None,
    age_max: Annotated[int | None, Query(ge=0, le=120)] = None,
) -> Page[MemberOut]:
    stmt = _member_query(db, scope, q, gender, status_ or None, anbiyam, age_min, age_max)
    stmt = apply_sort(
        stmt,
        params.sort,
        {
            "code": Member.code,
            "first_name": Member.first_name,
            "date_of_birth": Member.date_of_birth,
            "family": Family.family_name,
        },
        [Member.first_name, Member.id],
    )
    page = paginate(db, stmt, params, lambda m: m)
    units = _units(db, {m.family.anbiyam_id for m in page.items})
    return Page[MemberOut](
        items=[member_out(m, auth, units) for m in page.items],
        page=page.page,
        size=page.size,
        total=page.total,
        pages=page.pages,
    )


@members.get("/export")
def export_members(
    auth: Auth,
    scope: MemberExport,
    db: TenantSession,
    request: Request,
    q: Annotated[str | None, Query(max_length=100)] = None,
    gender: str | None = None,
    status_: Annotated[str | None, Query(alias="status")] = "ACTIVE",
    anbiyam: str | None = None,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    rows_m = [
        m
        for m in db.scalars(
            _member_query(
                db, auth.permissions.scope("member.view"), q, gender, status_ or None, anbiyam, None, None
            ).order_by(Member.code)
        )
        if scope.allows(m.family.anbiyam_id)
    ]
    units = _units(db, {m.family.anbiyam_id for m in rows_m})
    rows = []
    for m in rows_m:
        out = member_out(m, auth, units)
        rows.append(
            {
                **out.model_dump(),
                "family_code": out.family.code,
                "family_name": out.family.name,
                "anbiyam_name": out.anbiyam.name if out.anbiyam else "",
            }
        )
    _audit(
        db, auth, request, "EXPORT", "member", "register", remarks=f"{len(rows)} members as {format.value}"
    )
    cols = [
        Column("code", "Member ID", 12),
        Column("full_name", "Name"),
        Column("name_local", "Name (Tamil)"),
        Column("family_code", "Family ID"),
        Column("family_name", "Family"),
        Column("anbiyam_name", "Anbiyam"),
        Column("gender", "Gender"),
        Column("age", "Age", numeric=True),
        Column("relationship_to_head", "Relationship"),
        Column("status", "Status"),
    ]
    if auth.permissions.has("member.view_sensitive", anywhere=True):
        cols += [Column("date_of_birth", "Date of birth"), Column("phone", "Phone"), Column("email", "Email")]
    return export_table(
        rows,
        cols,
        format,
        title="Member register",
        filename="member-register",
        parish_name=auth.tenant.name,
        generated_by=auth.user.full_name,
    )


@members.get("/{member_id}", response_model=MemberOut)
def get_member(member_id: str, auth: Auth, scope: MemberView, db: TenantSession) -> MemberOut:
    m = svc.get_member(db, member_id, scope)
    return member_out(m, auth, _units(db, {m.family.anbiyam_id}))


@members.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: str, body: MemberUpdate, request: Request, auth: Auth, scope: MemberUpdateP, db: TenantSession
) -> MemberOut:
    m = svc.get_member(db, member_id, scope)
    data = body.model_dump(exclude_unset=True)
    unit = m.family.anbiyam_id
    _check_sacrament_write(auth, data, unit)
    _check_sensitive_write(auth, data, unit)
    if data.get("relationship_to_head") == "HEAD" and m.family.head_member_id != m.id:
        raise ValidationFailed(
            details=[{"field": "relationship_to_head", "message": "Use 'Set head of family'"}]
        )
    if (
        "relationship_to_head" in data
        and m.family.head_member_id == m.id
        and data["relationship_to_head"] != "HEAD"
    ):
        raise ValidationFailed(
            details=[{"field": "relationship_to_head", "message": "Choose another head first"}]
        )
    svc.apply_member_data(m, data)
    old, new = changes(m, exclude={"search_name", "phone_digits"})
    m.updated_by = auth.user.id
    _audit(db, auth, request, "UPDATE", "member", m.public_id, old=old, new=new)
    return member_out(m, auth, _units(db, {unit}))


@members.post("/{member_id}/deceased", response_model=MemberOut)
def mark_deceased(
    member_id: str, body: DeceasedIn, request: Request, auth: Auth, scope: MemberUpdateP, db: TenantSession
) -> MemberOut:
    m = svc.get_member(db, member_id, scope)
    svc.mark_deceased(db, m, date_of_death=body.date_of_death, remarks=body.remarks, actor=auth.user.id)
    _audit(db, auth, request, "DECEASED", "member", m.public_id, new=body.model_dump(mode="json"))
    return member_out(m, auth, _units(db, {m.family.anbiyam_id}))


@members.post("/{member_id}/status", response_model=MemberOut)
def member_status(
    member_id: str, body: StatusIn, request: Request, auth: Auth, scope: MemberUpdateP, db: TenantSession
) -> MemberOut:
    m = svc.get_member(db, member_id, scope)
    svc.set_member_status(db, m, body.active, reason=body.reason, actor=auth.user.id)
    _audit(db, auth, request, "STATUS_CHANGED", "member", m.public_id, new=body.model_dump())
    return member_out(m, auth, _units(db, {m.family.anbiyam_id}))


@members.post("/{member_id}/move", response_model=MemberOut)
def move_member(
    member_id: str, body: MoveMemberIn, request: Request, auth: Auth, _: FamilyTransfer, db: TenantSession
) -> MemberOut:
    view = auth.permissions.scope("member.view")
    m = svc.get_member(db, member_id, view)
    target = svc.get_family(db, body.family_id, auth.permissions.scope("family.view"))
    for fam in (m.family, target):
        _require(auth, "family.transfer", fam)
    new_head = svc.get_member(db, body.new_head_member_id) if body.new_head_member_id else None
    if new_head is not None and new_head.family_id != m.family_id:
        raise ValidationFailed(
            details=[{"field": "new_head_member_id", "message": "Must belong to the same family"}]
        )
    old_family = m.family.public_id
    svc.move_member(
        db,
        m,
        target,
        relationship=body.relationship_to_head,
        on=body.effective_date,
        reason=body.reason,
        actor=auth.user.id,
        new_head_for_old_family=new_head,
    )
    _audit(
        db,
        auth,
        request,
        "MOVED",
        "member",
        m.public_id,
        old={"family": old_family},
        new={"family": target.public_id, "reason": body.reason},
    )
    db.flush()
    db.refresh(m)
    return member_out(m, auth, _units(db, {target.anbiyam_id}))


@members.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: str, request: Request, auth: Auth, scope: MemberDelete, db: TenantSession
) -> Response:
    """Remove a member entered by mistake. Real-life changes use status, deceased or move instead."""
    m = svc.get_member(db, member_id, scope)
    if m.family.head_member_id == m.id:
        raise ValidationFailed("Choose another head of family first", code="FAMILY_HEAD_REQUIRED")
    svc.end_memberships(db, member_ids=[m.id], on=date.today(), reason="Removed")
    m.soft_delete(auth.user.id)
    svc.event(db, m.family, "MEMBER_REMOVED", actor=auth.user.id, member=m, member_name=m.full_name)
    _audit(db, auth, request, "DELETE", "member", m.public_id, old={"code": m.code, "name": m.full_name})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@members.get("/{member_id}/memberships", response_model=list[MembershipOut])
def member_memberships(
    member_id: str, auth: Auth, scope: MemberView, db: TenantSession, include_history: bool = False
) -> list[MembershipOut]:
    m = svc.get_member(db, member_id, scope)
    stmt = select(OrgUnitMembership).where(
        or_(OrgUnitMembership.member_id == m.id, OrgUnitMembership.family_id == m.family_id)
    )
    if not include_history:
        stmt = stmt.where(OrgUnitMembership.left_on.is_(None))
    rows = list(db.scalars(stmt.order_by(OrgUnitMembership.joined_on.desc())))
    units = _units(db, {r.org_unit_id for r in rows} | {m.family.anbiyam_id})
    out = [_membership_out(r, units, {m.id: m}, {m.family_id: m.family}) for r in rows]
    if m.family.anbiyam_id and m.family.anbiyam_id in units:
        out.insert(
            0,
            MembershipOut(
                id=None,
                org_unit=_ref_unit(units[m.family.anbiyam_id]),
                member=None,  # type: ignore[arg-type]
                family=_ref_family(m.family),
                joined_on=None,
                left_on=None,
                current=True,
            ),
        )
    return out


# ============================================================================ organisation memberships
def _membership_out(
    r: OrgUnitMembership, units: dict[int, OrgUnit], mems: dict[int, Member], fams: dict[int, Family]
) -> MembershipOut:
    m = mems.get(r.member_id) if r.member_id else None
    f = fams.get(r.family_id) if r.family_id else None
    return MembershipOut(
        id=r.public_id,
        org_unit=_ref_unit(units[r.org_unit_id]),  # type: ignore[arg-type]
        member=Ref(id=m.public_id, code=m.code, name=m.full_name) if m else None,
        family=_ref_family(f) if f else (_ref_family(m.family) if m else None),
        gender=m.gender if m else None,
        age=svc.age_on(m.date_of_birth) if m else None,
        joined_on=r.joined_on,
        left_on=r.left_on,
        current=r.left_on is None,
        remarks=r.remarks,
    )


def _visible_unit(db: Session, unit_id: str, scope: PermissionScope) -> OrgUnit:
    u = db.scalars(select(OrgUnit).where(OrgUnit.public_id == unit_id, OrgUnit.is_deleted.is_(False))).first()
    if u is None or not scope.allows(u.id):
        raise NotFound()
    return u


@memberships.get("/{unit_id}/memberships", response_model=Page[MembershipOut])
def unit_memberships(
    unit_id: str,
    scope: OrgView,
    db: TenantSession,
    params: PageQuery,
    include_history: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[MembershipOut]:
    """Members of an organisation. For an Anbiyam this lists its families."""
    unit = _visible_unit(db, unit_id, scope)
    units = {unit.id: unit}
    if unit.type.code == svc.ANBIYAM:
        stmt = select(Family).where(
            Family.anbiyam_id == unit.id,
            Family.is_deleted.is_(False),
            Family.status.in_([FamilyStatus.ACTIVE, FamilyStatus.INACTIVE]),
        )
        if q:
            stmt = stmt.where(Family.search_name.like(f"%{svc.normalize_name(q)}%"))
        page = paginate(db, stmt.order_by(Family.family_name), params, lambda f: f)
        return Page[MembershipOut](
            items=[
                MembershipOut(
                    id=None,
                    org_unit=_ref_unit(unit),
                    member=None,  # type: ignore[arg-type]
                    family=_ref_family(f),
                    joined_on=None,
                    left_on=None,
                    current=True,
                )
                for f in page.items
            ],
            page=page.page,
            size=page.size,
            total=page.total,
            pages=page.pages,
        )
    stmt = select(OrgUnitMembership).where(OrgUnitMembership.org_unit_id == unit.id)
    if not include_history:
        stmt = stmt.where(OrgUnitMembership.left_on.is_(None))
    if q:
        stmt = (
            stmt.outerjoin(Member, Member.id == OrgUnitMembership.member_id)
            .outerjoin(Family, Family.id == OrgUnitMembership.family_id)
            .where(
                or_(
                    Member.search_name.like(f"%{svc.normalize_name(q)}%"),
                    Family.search_name.like(f"%{svc.normalize_name(q)}%"),
                )
            )
        )
    page = paginate(
        db,
        stmt.order_by(OrgUnitMembership.left_on.is_not(None), OrgUnitMembership.joined_on.desc()),
        params,
        lambda r: r,
    )
    mems = {
        m.id: m
        for m in db.scalars(
            select(Member).where(Member.id.in_({r.member_id for r in page.items if r.member_id}))
        )
    }
    fams = {
        f.id: f
        for f in db.scalars(
            select(Family).where(Family.id.in_({r.family_id for r in page.items if r.family_id}))
        )
    }
    return Page[MembershipOut](
        items=[_membership_out(r, units, mems, fams) for r in page.items],
        page=page.page,
        size=page.size,
        total=page.total,
        pages=page.pages,
    )


@memberships.post("/{unit_id}/memberships", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
def add_membership(
    unit_id: str, body: MembershipIn, request: Request, auth: Auth, scope: OrgManage, db: TenantSession
) -> MembershipOut:
    unit = _visible_unit(db, unit_id, scope)
    member = svc.get_member(db, body.member_id) if body.member_id else None
    family = svc.get_family(db, body.family_id) if body.family_id else None
    ms = svc.join(
        db,
        unit,
        member=member,
        family=family,
        joined_on=body.joined_on,
        remarks=body.remarks,
        actor=auth.user.id,
    )
    _audit(
        db,
        auth,
        request,
        "MEMBERSHIP_ADDED",
        "org_unit",
        unit.public_id,
        new={"member": body.member_id, "family": body.family_id, "joined_on": ms.joined_on},
    )
    return _membership_out(
        ms, {unit.id: unit}, {member.id: member} if member else {}, {family.id: family} if family else {}
    )


@memberships.post("/{unit_id}/memberships/{membership_id}/end", response_model=MembershipOut)
def end_membership(
    unit_id: str,
    membership_id: str,
    body: MembershipEndIn,
    request: Request,
    auth: Auth,
    scope: OrgManage,
    db: TenantSession,
) -> MembershipOut:
    unit = _visible_unit(db, unit_id, scope)
    ms = db.scalars(
        select(OrgUnitMembership).where(
            OrgUnitMembership.public_id == membership_id, OrgUnitMembership.org_unit_id == unit.id
        )
    ).first()
    if ms is None:
        raise NotFound()
    if ms.left_on is not None:
        raise ValidationFailed("This membership has already ended", code="INVALID_STATE")
    left = body.left_on or date.today()
    if left < ms.joined_on:
        raise ValidationFailed(details=[{"field": "left_on", "message": "Before the joining date"}])
    ms.left_on, ms.end_reason = left, body.reason or "Left"
    _audit(
        db,
        auth,
        request,
        "MEMBERSHIP_ENDED",
        "org_unit",
        unit.public_id,
        new={"membership": ms.public_id, "left_on": left},
    )
    mems = {ms.member_id: db.get(Member, ms.member_id)} if ms.member_id else {}
    fams = {ms.family_id: db.get(Family, ms.family_id)} if ms.family_id else {}
    return _membership_out(ms, {unit.id: unit}, mems, fams)  # type: ignore[arg-type]

"""Parish profile (``/api/v1/parish``) and priests (``/api/v1/priests``)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.audit import changes, record_audit
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.parish import service as svc
from app.modules.parish.models import Priest, PriestAssignment
from app.modules.parish.schemas import (
    AppointIn,
    ClergyOut,
    LinkUserIn,
    PriestAssignmentOut,
    PriestIn,
    PriestOut,
    PriestStatusIn,
    PriestUpdate,
    ProfileOut,
    ProfileUpdate,
    RelieveIn,
)
from app.modules.rbac.deps import require_perm
from app.modules.rbac.service import PermissionScope
from app.tenancy.deps import TenantSession

parish_router = APIRouter(prefix="/parish", tags=["parish"])
priests_router = APIRouter(prefix="/priests", tags=["priests"])
MODULE = "parish"


def _p(code: str):  # type: ignore[no-untyped-def]
    return Annotated[PermissionScope, Depends(require_perm(code, parish_wide=True))]


CanUpdateSettings = _p("settings.update")
CanViewPriests, CanCreatePriests, CanUpdatePriests = (
    _p("priest.view"),
    _p("priest.create"),
    _p("priest.update"),
)


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


# ============================================================================ profile
def _profile_out(db: Session, auth: Auth) -> ProfileOut:
    p = svc.get_profile(db, auth.tenant)
    pp = svc.current_parish_priest(db)
    from app.db.master import master_session
    from app.master.models import Parish

    with master_session() as ms:
        parish = ms.get(Parish, auth.tenant.parish_id)
        diocese = parish.diocese.name if parish else ""
    return ProfileOut(
        **{f: getattr(p, f) for f in svc.PROFILE_FIELDS},
        logo_url=svc.logo_url(p),
        code=auth.tenant.code,
        diocese_name=diocese,
        parish_priest=pp.priest.display_name if pp else None,
        updated_at=p.updated_at,
    )


@parish_router.get("/profile", response_model=ProfileOut)
def get_profile(auth: Auth, db: TenantSession) -> ProfileOut:
    """Basic parish information – visible to every signed-in user."""
    return _profile_out(db, auth)


@parish_router.patch("/profile", response_model=ProfileOut)
def update_profile(
    body: ProfileUpdate, request: Request, auth: Auth, _: CanUpdateSettings, db: TenantSession
) -> ProfileOut:
    p = svc.get_profile(db, auth.tenant)
    data = body.model_dump(exclude_unset=True)
    for required in ("name", "default_language", "currency", "timezone", "fy_start_month"):
        if required in data and data[required] is None:
            raise ValidationFailed(details=[{"field": required, "message": "Required"}])
    svc.update_profile(p, data, auth.user.id)
    old, new = changes(p, exclude={"updated_by"})
    _audit(db, auth, request, "UPDATE", "parish_profile", auth.tenant.public_id, old=old, new=new)
    db.flush()
    svc.sync_to_master(auth.tenant, p)
    return _profile_out(db, auth)


@parish_router.post("/profile/logo", response_model=ProfileOut)
async def upload_logo(
    request: Request,
    auth: Auth,
    _: CanUpdateSettings,
    db: TenantSession,
    file: Annotated[UploadFile, File(description="PNG or JPEG, max 2 MB")],
) -> ProfileOut:
    data = await file.read(svc.LOGO_MAX_BYTES + 1)
    p = svc.get_profile(db, auth.tenant)
    svc.set_logo(p, auth.tenant, file.filename or "logo", data)
    _audit(
        db,
        auth,
        request,
        "LOGO_UPDATED",
        "parish_profile",
        auth.tenant.public_id,
        new={"file": file.filename, "size": len(data)},
    )
    db.flush()
    svc.sync_to_master(auth.tenant, p)
    return _profile_out(db, auth)


@parish_router.delete("/profile/logo", response_model=ProfileOut)
def delete_logo(request: Request, auth: Auth, _: CanUpdateSettings, db: TenantSession) -> ProfileOut:
    p = svc.get_profile(db, auth.tenant)
    svc.remove_logo(p)
    _audit(db, auth, request, "LOGO_REMOVED", "parish_profile", auth.tenant.public_id)
    db.flush()
    svc.sync_to_master(auth.tenant, p)
    return _profile_out(db, auth)


@parish_router.get("/clergy", response_model=ClergyOut)
def clergy(auth: Auth, db: TenantSession) -> ClergyOut:
    """Priests serving the parish today (names and roles only) – for every signed-in user."""
    del auth
    rows = list(db.scalars(svc.current_assignments_stmt().order_by(PriestAssignment.appointed_on)))
    pp = next((a for a in rows if a.role == svc.PARISH_PRIEST), None)

    def brief(a: PriestAssignment) -> dict[str, str]:
        return {
            "id": a.priest.public_id,
            "name": a.priest.display_name,
            "role": a.role,
            "since": a.appointed_on.isoformat(),
        }

    return ClergyOut(parish_priest=brief(pp) if pp else None, others=[brief(a) for a in rows if a is not pp])


# ============================================================================ priests
def _assignment_out(a: PriestAssignment) -> PriestAssignmentOut:
    return PriestAssignmentOut(
        id=a.public_id,
        role=a.role,
        appointed_on=a.appointed_on,
        relieved_on=a.relieved_on,
        current=a.is_current(date.today()),
        responsibilities=a.responsibilities,
        appointment_ref=a.appointment_ref,
        relieving_reason=a.relieving_reason,
        remarks=a.remarks,
        grants_role=a.role_assignment_id is not None,
    )


def _priest_out(db: Session, p: Priest) -> PriestOut:
    user = db.get(User, p.user_id) if p.user_id else None
    today = date.today()
    return PriestOut(
        id=p.public_id,
        title=p.title,
        full_name=p.full_name,
        display_name=p.display_name,
        name_local=p.name_local,
        date_of_birth=p.date_of_birth,
        ordination_date=p.ordination_date,
        clergy_type=p.clergy_type,
        home_diocese=p.home_diocese,
        congregation=p.congregation,
        phone=p.phone,
        email=p.email,
        status=p.status,
        user={"id": user.public_id, "username": user.username, "full_name": user.full_name} if user else None,
        remarks=p.remarks,
        current_roles=sorted({a.role for a in p.assignments if a.is_current(today)}),
        assignments=[_assignment_out(a) for a in p.assignments],
        created_at=p.created_at,
    )


def _get(db: Session, priest_id: str) -> Priest:
    p = db.scalars(select(Priest).where(Priest.public_id == priest_id, Priest.is_deleted.is_(False))).first()
    if p is None:
        raise NotFound()
    return p


@priests_router.get("", response_model=Page[PriestOut])
def list_priests(
    _: CanViewPriests,
    db: TenantSession,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    serving: Annotated[bool | None, Query(description="Only priests with a current assignment")] = None,
) -> Page[PriestOut]:
    stmt = select(Priest).where(Priest.is_deleted.is_(False))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Priest.full_name.ilike(like),
                Priest.name_local.ilike(like),
                Priest.congregation.ilike(like),
                Priest.home_diocese.ilike(like),
            )
        )
    if status_:
        stmt = stmt.where(Priest.status == status_)
    if serving is not None:
        ids = select(PriestAssignment.priest_id).where(svc.current_assignments_stmt().whereclause)  # type: ignore[arg-type]
        stmt = stmt.where(Priest.id.in_(ids) if serving else Priest.id.not_in(ids))
    stmt = apply_sort(
        stmt,
        params.sort,
        {
            "full_name": Priest.full_name,
            "ordination_date": Priest.ordination_date,
            "created_at": Priest.created_at,
        },
        [Priest.full_name, Priest.id],
    )
    return paginate(db, stmt, params, lambda p: _priest_out(db, p))


@priests_router.post("", response_model=PriestOut, status_code=status.HTTP_201_CREATED)
def create_priest(
    body: PriestIn, request: Request, auth: Auth, _: CanCreatePriests, db: TenantSession
) -> PriestOut:
    p = Priest(**body.model_dump(), created_by=auth.user.id)
    db.add(p)
    db.flush()
    db.refresh(p)
    _audit(db, auth, request, "CREATE", "priest", p.public_id, new=body.model_dump(mode="json"))
    return _priest_out(db, p)


@priests_router.get("/{priest_id}", response_model=PriestOut)
def get_priest(priest_id: str, _: CanViewPriests, db: TenantSession) -> PriestOut:
    return _priest_out(db, _get(db, priest_id))


@priests_router.patch("/{priest_id}", response_model=PriestOut)
def update_priest(
    priest_id: str, body: PriestUpdate, request: Request, auth: Auth, _: CanUpdatePriests, db: TenantSession
) -> PriestOut:
    p = _get(db, priest_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    old, new = changes(p)
    p.updated_by = auth.user.id
    _audit(db, auth, request, "UPDATE", "priest", p.public_id, old=old, new=new)
    return _priest_out(db, p)


@priests_router.post("/{priest_id}/status", response_model=PriestOut)
def priest_status(
    priest_id: str, body: PriestStatusIn, request: Request, auth: Auth, _: CanUpdatePriests, db: TenantSession
) -> PriestOut:
    p = _get(db, priest_id)
    old = p.status
    ended = svc.set_status(db, p, body.status, auth.user.id)
    _audit(
        db,
        auth,
        request,
        "STATUS_CHANGED",
        "priest",
        p.public_id,
        old={"status": old},
        new={"status": body.status},
        remarks=f"{ended} assignment(s) relieved" if ended else None,
    )
    db.flush()
    db.refresh(p)
    return _priest_out(db, p)


@priests_router.post("/{priest_id}/user", response_model=PriestOut)
def link_user(
    priest_id: str, body: LinkUserIn, request: Request, auth: Auth, _: CanUpdatePriests, db: TenantSession
) -> PriestOut:
    """Link the priest's user account.

    A current Parish Priest assignment then grants the PARISH_PRIEST role.
    """
    if not auth.permissions.has("user.assign_role"):
        raise PermissionDenied(
            "Linking a user account can grant the Parish Priest role",
            details=[{"field": "permission", "message": "user.assign_role"}],
        )
    p = _get(db, priest_id)
    user = None
    if body.user_id:
        user = db.scalars(
            select(User).where(User.public_id == body.user_id, User.is_deleted.is_(False))
        ).first()
        if user is None:
            raise ValidationFailed(details=[{"field": "user_id", "message": "User not found"}])
        if user.id == auth.user.id:
            raise PermissionDenied("You cannot link your own account", code="SELF_MODIFICATION")
    svc.link_user(db, p, user, auth.user.id)
    _audit(
        db,
        auth,
        request,
        "USER_LINKED" if user else "USER_UNLINKED",
        "priest",
        p.public_id,
        new={"user": body.user_id},
    )
    db.flush()
    db.refresh(p)
    return _priest_out(db, p)


@priests_router.post(
    "/{priest_id}/assignments", response_model=PriestOut, status_code=status.HTTP_201_CREATED
)
def appoint(
    priest_id: str, body: AppointIn, request: Request, auth: Auth, _: CanUpdatePriests, db: TenantSession
) -> PriestOut:
    p = _get(db, priest_id)
    a = svc.appoint(db, p, **body.model_dump(), actor=auth.user.id)
    _audit(
        db,
        auth,
        request,
        "APPOINTED",
        "priest",
        p.public_id,
        new={**body.model_dump(mode="json"), "assignment": a.public_id},
    )
    db.flush()
    db.expire_all()
    return _priest_out(db, _get(db, priest_id))


@priests_router.post("/{priest_id}/assignments/{assignment_id}/relieve", response_model=PriestOut)
def relieve(
    priest_id: str,
    assignment_id: str,
    body: RelieveIn,
    request: Request,
    auth: Auth,
    _: CanUpdatePriests,
    db: TenantSession,
) -> PriestOut:
    p = _get(db, priest_id)
    a = next((x for x in p.assignments if x.public_id == assignment_id), None)
    if a is None:
        raise NotFound()
    svc.relieve(db, a, relieved_on=body.relieved_on, reason=body.reason, actor=auth.user.id)
    _audit(
        db,
        auth,
        request,
        "RELIEVED",
        "priest",
        p.public_id,
        new={"assignment": a.public_id, **body.model_dump(mode="json")},
    )
    db.flush()
    db.expire_all()
    return _priest_out(db, _get(db, priest_id))

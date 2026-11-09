"""Platform console APIs (``/api/v1/platform``): auth, dioceses, parishes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.tenant import tenant_session_scope
from app.master.auth import (
    CurrentPlatformUser,
    MasterSession,
    SuperAdmin,
    allowed_diocese_ids,
    authenticate_platform_user,
    issue_platform_token,
)
from app.master.models import Diocese, Parish, ParishStatus, PlatformAuditLog
from app.master.schemas import (
    DioceseCreate,
    DioceseOut,
    DioceseUpdate,
    ParishCreate,
    ParishOut,
    ParishStatusUpdate,
    PlatformLoginIn,
    PlatformTokenOut,
    PlatformUserOut,
)
from app.modules.identity.service import create_initial_admin
from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish
from app.tenancy.resolver import invalidate_tenant

router = APIRouter(prefix="/platform", tags=["platform"])


def _audit(
    session: Any,
    request: Request,
    actor_id: int,
    action: str,
    entity: str,
    entity_id: str,
    new: dict[str, Any] | None = None,
    old: dict[str, Any] | None = None,
    parish_id: int | None = None,
) -> None:
    session.add(
        PlatformAuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity,
            entity_id=entity_id,
            parish_id=parish_id,
            ip=request.client.host if request.client else None,
            new_values=new,
            old_values=old,
        )
    )


# ------------------------------------------------------------------------------ auth
@router.post("/auth/login", response_model=PlatformTokenOut)
def platform_login(body: PlatformLoginIn, session: MasterSession, request: Request) -> PlatformTokenOut:
    user = authenticate_platform_user(session, body.email, body.password, request)
    token, expires_in = issue_platform_token(user)
    return PlatformTokenOut(access_token=token, expires_in=expires_in)


@router.get("/auth/me", response_model=PlatformUserOut)
def platform_me(user: CurrentPlatformUser) -> Any:
    return user


# ------------------------------------------------------------------------------ dioceses
def _get_diocese(session: Any, public_id: str, user: Any) -> Diocese:
    diocese = session.scalars(
        select(Diocese).where(Diocese.public_id == public_id, Diocese.is_deleted.is_(False))
    ).first()
    allowed = allowed_diocese_ids(session, user)
    if diocese is None or (allowed is not None and diocese.id not in allowed):
        raise NotFound()
    return diocese


@router.get("/dioceses", response_model=Page[DioceseOut])
def list_dioceses(
    session: MasterSession,
    user: CurrentPlatformUser,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
) -> Page[DioceseOut]:
    stmt = select(Diocese).where(Diocese.is_deleted.is_(False))
    allowed = allowed_diocese_ids(session, user)
    if allowed is not None:
        stmt = stmt.where(Diocese.id.in_(allowed or {-1}))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Diocese.name.ilike(like), Diocese.code.ilike(like)))
    if status_:
        stmt = stmt.where(Diocese.status == status_)
    stmt = apply_sort(
        stmt,
        params.sort,
        {"name": Diocese.name, "code": Diocese.code, "created_at": Diocese.created_at},
        [Diocese.name],
    )
    return paginate(session, stmt, params, DioceseOut.model_validate)


@router.post("/dioceses", response_model=DioceseOut, status_code=status.HTTP_201_CREATED)
def create_diocese(body: DioceseCreate, session: MasterSession, user: SuperAdmin, request: Request) -> Any:
    code = body.code.upper()
    if session.scalars(select(Diocese.id).where(Diocese.code == code)).first() is not None:
        raise Conflict("A diocese with this code already exists", code="DIOCESE_CODE_EXISTS")
    data = body.model_dump()
    data["code"] = code
    diocese = Diocese(**data, created_by=user.id)
    session.add(diocese)
    session.flush()
    _audit(
        session, request, user.id, "CREATE", "diocese", diocese.public_id, new=body.model_dump(mode="json")
    )
    return diocese


@router.get("/dioceses/{diocese_id}", response_model=DioceseOut)
def get_diocese(diocese_id: str, session: MasterSession, user: CurrentPlatformUser) -> Any:
    return _get_diocese(session, diocese_id, user)


@router.patch("/dioceses/{diocese_id}", response_model=DioceseOut)
def update_diocese(
    diocese_id: str, body: DioceseUpdate, session: MasterSession, user: SuperAdmin, request: Request
) -> Any:
    diocese = _get_diocese(session, diocese_id, user)
    changes = body.model_dump(exclude_unset=True)
    old = {k: getattr(diocese, k) for k in changes}
    for key, value in changes.items():
        setattr(diocese, key, value)
    diocese.updated_by = user.id
    _audit(
        session,
        request,
        user.id,
        "UPDATE",
        "diocese",
        diocese.public_id,
        new=body.model_dump(mode="json", exclude_unset=True),
        old={k: str(v) for k, v in old.items()},
    )
    return diocese


# ------------------------------------------------------------------------------ parishes
def _parish_out(p: Parish) -> ParishOut:
    return ParishOut(
        id=p.public_id,
        code=p.code,
        subdomain=p.subdomain,
        name=p.name,
        status=p.status,
        diocese_code=p.diocese.code,
        diocese_name=p.diocese.name,
        city=p.city,
        established_on=p.established_on,
        schema_version=p.database.schema_version if p.database else None,
        last_error=p.database.last_error if p.database else None,
        created_at=p.created_at,
    )


def _get_parish(session: Any, public_id: str, user: Any) -> Parish:
    parish = session.scalars(
        select(Parish)
        .options(joinedload(Parish.diocese), joinedload(Parish.database))
        .where(Parish.public_id == public_id, Parish.is_deleted.is_(False))
    ).first()
    allowed = allowed_diocese_ids(session, user)
    if parish is None or (allowed is not None and parish.diocese_id not in allowed):
        raise NotFound()
    return parish


@router.get("/parishes", response_model=Page[ParishOut])
def list_parishes(
    session: MasterSession,
    user: CurrentPlatformUser,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    diocese: Annotated[str | None, Query(description="Diocese public id")] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
) -> Page[ParishOut]:
    stmt = (
        select(Parish)
        .join(Parish.diocese)
        .options(joinedload(Parish.diocese), joinedload(Parish.database))
        .where(Parish.is_deleted.is_(False))
    )
    allowed = allowed_diocese_ids(session, user)
    if allowed is not None:
        stmt = stmt.where(Parish.diocese_id.in_(allowed or {-1}))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Parish.name.ilike(like), Parish.code.ilike(like), Parish.city.ilike(like)))
    if diocese:
        stmt = stmt.where(Diocese.public_id == diocese)
    if status_:
        stmt = stmt.where(Parish.status == status_)
    stmt = apply_sort(
        stmt,
        params.sort,
        {"name": Parish.name, "code": Parish.code, "created_at": Parish.created_at},
        [Parish.name],
    )
    return paginate(session, stmt, params, _parish_out)


@router.post("/parishes", response_model=ParishOut, status_code=status.HTTP_201_CREATED)
def create_parish(
    body: ParishCreate, session: MasterSession, user: SuperAdmin, request: Request
) -> ParishOut:
    """Register a parish and provision its dedicated database (migrate + seed)."""
    if body.admin_username and not body.admin_email:
        raise ValidationFailed(details=[{"field": "admin_email", "message": "Required with admin_username"}])
    reg = ParishRegistration(
        **body.model_dump(
            exclude={"address_line2", "country", "admin_username", "admin_full_name", "admin_email"}
        )
    )
    parish = register_parish(session, reg, actor_id=user.id)
    _audit(
        session,
        request,
        user.id,
        "CREATE",
        "parish",
        parish.public_id,
        new=body.model_dump(mode="json"),
        parish_id=parish.id,
    )
    session.commit()
    try:
        tenant = provision_parish(parish.code)
    finally:
        session.expire_all()
    if body.admin_username and body.admin_email:
        with tenant_session_scope(tenant) as tsession:
            create_initial_admin(
                tsession,
                tenant,
                username=body.admin_username,
                full_name=body.admin_full_name or "Parish Administrator",
                email=str(body.admin_email),
            )
    out = _parish_out(_get_parish(session, parish.public_id, user))
    out.admin_username = body.admin_username.lower() if body.admin_username else None
    return out


@router.get("/parishes/{parish_id}", response_model=ParishOut)
def get_parish(parish_id: str, session: MasterSession, user: CurrentPlatformUser) -> ParishOut:
    return _parish_out(_get_parish(session, parish_id, user))


@router.post("/parishes/{parish_id}/provision", response_model=ParishOut)
def reprovision_parish(
    parish_id: str, session: MasterSession, user: SuperAdmin, request: Request
) -> ParishOut:
    """Re-run provisioning (idempotent) – used after a FAILED provisioning."""
    parish = _get_parish(session, parish_id, user)
    _audit(session, request, user.id, "PROVISION", "parish", parish.public_id, parish_id=parish.id)
    session.commit()
    provision_parish(parish.code)
    session.expire_all()
    return _parish_out(_get_parish(session, parish_id, user))


@router.patch("/parishes/{parish_id}/status", response_model=ParishOut)
def update_parish_status(
    parish_id: str, body: ParishStatusUpdate, session: MasterSession, user: SuperAdmin, request: Request
) -> ParishOut:
    parish = _get_parish(session, parish_id, user)
    if parish.status in (ParishStatus.PROVISIONING, ParishStatus.FAILED):
        raise Conflict("Parish has not been provisioned", code="INVALID_STATE")
    old = parish.status
    parish.status = body.status
    parish.updated_by = user.id
    _audit(
        session,
        request,
        user.id,
        "STATUS_CHANGE",
        "parish",
        parish.public_id,
        old={"status": old},
        new={"status": body.status, "remarks": body.remarks},
        parish_id=parish.id,
    )
    session.flush()
    invalidate_tenant(parish.code, parish.subdomain)
    return _parish_out(parish)

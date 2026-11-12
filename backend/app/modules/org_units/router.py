"""Organisation APIs: ``/api/v1/org-unit-types`` and ``/api/v1/org-units``.

Authorization:
* type & position configuration – parish-wide ``org_unit.create/update/delete``;
* units – ``org_unit.view`` (scoped holders see only their units and sub-units), parish-wide create/delete,
  scoped ``org_unit.update``;
* office bearers – ``org_unit.manage_members`` for that unit. Appointing to a position that grants a
  parish-wide role additionally requires parish-wide ``user.assign_role``; nobody can appoint themselves
  to a role-granting position.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import changes, record_audit
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.org_units import service
from app.modules.org_units.models import OrgUnit, OrgUnitOfficeBearer, OrgUnitPosition, OrgUnitType
from app.modules.org_units.schemas import (
    BearerCreate,
    BearerEnd,
    BearerOut,
    MyUnitsOut,
    PositionIn,
    PositionOut,
    PositionUpdate,
    ScopedUnit,
    TypeCreate,
    TypeOut,
    TypeUpdate,
    UnitBrief,
    UnitCreate,
    UnitOut,
    UnitUpdate,
)
from app.modules.rbac.deps import require_perm
from app.modules.rbac.models import Role
from app.modules.rbac.service import PermissionScope
from app.tenancy.deps import TenantSession

types_router = APIRouter(prefix="/org-unit-types", tags=["organisations"])
units_router = APIRouter(prefix="/org-units", tags=["organisations"])
MODULE = "org_units"


def _scope(code: str, parish_wide: bool = False):  # type: ignore[no-untyped-def]
    return Annotated[PermissionScope, Depends(require_perm(code, parish_wide=parish_wide))]


CanView = _scope("org_unit.view")
CanCreate = _scope("org_unit.create", parish_wide=True)
CanUpdate = _scope("org_unit.update")
CanUpdateParish = _scope("org_unit.update", parish_wide=True)
CanDelete = _scope("org_unit.delete", parish_wide=True)
CanManageMembers = _scope("org_unit.manage_members")


# ============================================================================ types
def _position_out(p: OrgUnitPosition, roles: dict[int, Role]) -> PositionOut:
    role = roles.get(p.role_id) if p.role_id else None
    return PositionOut(
        id=p.public_id,
        code=p.code,
        name=p.name,
        name_local=p.name_local,
        role_code=role.code if role else None,
        role_name=role.name if role else None,
        max_holders=p.max_holders,
        sort_order=p.sort_order,
    )


def _type_out(db: Session, t: OrgUnitType) -> TypeOut:
    roles = {r.id: r for r in db.scalars(select(Role))}
    units = db.scalar(
        select(func.count())
        .select_from(OrgUnit)
        .where(OrgUnit.type_id == t.id, OrgUnit.is_deleted.is_(False))
    )
    return TypeOut(
        id=t.public_id,
        code=t.code,
        name=t.name,
        name_plural=t.name_plural,
        name_local=t.name_local,
        description=t.description,
        member_kind=t.member_kind,
        membership_rules=t.membership_rules or {},
        allow_multiple_units=t.allow_multiple_units,
        code_prefix=t.code_prefix,
        is_system=t.is_system,
        sort_order=t.sort_order,
        unit_count=units or 0,
        positions=[_position_out(p, roles) for p in t.positions],
    )


def _add_position(db: Session, t: OrgUnitType, p: PositionIn) -> OrgUnitPosition:
    code = p.code.upper()
    clash = db.scalars(
        select(OrgUnitPosition.id).where(OrgUnitPosition.type_id == t.id, OrgUnitPosition.code == code)
    ).first()
    if clash is not None:
        raise Conflict("A position with this code already exists", code="POSITION_CODE_EXISTS")
    pos = OrgUnitPosition(
        type_id=t.id,
        code=code,
        name=p.name,
        name_local=p.name_local,
        role_id=service.resolve_role_for_position(db, p.role_code),
        max_holders=p.max_holders,
        sort_order=p.sort_order,
    )
    db.add(pos)
    db.flush()
    return pos


@types_router.get("", response_model=list[TypeOut])
def list_types(_: CanView, db: TenantSession) -> list[TypeOut]:
    rows = db.scalars(
        select(OrgUnitType)
        .where(OrgUnitType.is_deleted.is_(False))
        .order_by(OrgUnitType.sort_order, OrgUnitType.name)
    )
    return [_type_out(db, t) for t in rows]


@types_router.get("/{type_id}", response_model=TypeOut)
def get_type(type_id: str, _: CanView, db: TenantSession) -> TypeOut:
    return _type_out(db, service.get_type(db, type_id))


@types_router.post("", response_model=TypeOut, status_code=status.HTTP_201_CREATED)
def create_type(body: TypeCreate, request: Request, auth: Auth, _: CanCreate, db: TenantSession) -> TypeOut:
    code = body.code.upper()
    if db.scalars(select(OrgUnitType.id).where(OrgUnitType.code == code)).first() is not None:
        raise Conflict("A type with this code already exists", code="TYPE_CODE_EXISTS")
    t = OrgUnitType(
        code=code,
        name=body.name,
        name_plural=body.name_plural,
        name_local=body.name_local,
        description=body.description,
        member_kind=body.member_kind,
        membership_rules=body.membership_rules.model_dump(exclude_none=True),
        allow_multiple_units=body.allow_multiple_units,
        code_prefix=body.code_prefix.upper(),
        sort_order=body.sort_order,
        is_system=False,
        created_by=auth.user.id,
    )
    db.add(t)
    db.flush()
    for p in body.positions:
        _add_position(db, t, p)
    db.refresh(t)
    record_audit(
        db,
        action="CREATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit_type",
        entity_id=t.public_id,
        new=body.model_dump(mode="json"),
    )
    return _type_out(db, t)


@types_router.patch("/{type_id}", response_model=TypeOut)
def update_type(
    type_id: str, body: TypeUpdate, request: Request, auth: Auth, _: CanUpdateParish, db: TenantSession
) -> TypeOut:
    t = service.get_type(db, type_id)
    data = body.model_dump(exclude_unset=True)
    if "membership_rules" in data and body.membership_rules is not None:
        data["membership_rules"] = body.membership_rules.model_dump(exclude_none=True)
    if data.get("allow_multiple_units") is False:
        n = db.scalar(
            select(func.count())
            .select_from(OrgUnit)
            .where(OrgUnit.type_id == t.id, OrgUnit.is_deleted.is_(False))
        )
        if (n or 0) > 1:
            raise Conflict("More than one organisation of this type exists", code="SINGLE_UNIT_TYPE")
    for k, v in data.items():
        setattr(t, k, v)
    old, new = changes(t)
    t.updated_by = auth.user.id
    record_audit(
        db,
        action="UPDATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit_type",
        entity_id=t.public_id,
        old=old,
        new=new,
    )
    return _type_out(db, t)


@types_router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_type(type_id: str, request: Request, auth: Auth, _: CanDelete, db: TenantSession) -> Response:
    t = service.get_type(db, type_id)
    if t.is_system:
        raise Conflict("Built-in organisation types cannot be deleted", code="SYSTEM_TYPE")
    if db.scalars(select(OrgUnit.id).where(OrgUnit.type_id == t.id, OrgUnit.is_deleted.is_(False))).first():
        raise Conflict("Archive or move this type's organisations first", code="TYPE_IN_USE")
    t.soft_delete(auth.user.id)
    record_audit(
        db,
        action="DELETE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit_type",
        entity_id=t.public_id,
        old={"code": t.code},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@types_router.post("/{type_id}/positions", response_model=TypeOut, status_code=status.HTTP_201_CREATED)
def add_position(
    type_id: str, body: PositionIn, request: Request, auth: Auth, _: CanUpdateParish, db: TenantSession
) -> TypeOut:
    t = service.get_type(db, type_id)
    pos = _add_position(db, t, body)
    record_audit(
        db,
        action="CREATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit_position",
        entity_id=pos.public_id,
        new=body.model_dump(),
    )
    db.expire(t)
    return _type_out(db, t)


def _get_position(db: Session, t: OrgUnitType, position_id: str) -> OrgUnitPosition:
    p = db.scalars(
        select(OrgUnitPosition).where(
            OrgUnitPosition.public_id == position_id,
            OrgUnitPosition.type_id == t.id,
            OrgUnitPosition.is_deleted.is_(False),
        )
    ).first()
    if p is None:
        raise NotFound()
    return p


@types_router.patch("/{type_id}/positions/{position_id}", response_model=TypeOut)
def update_position(
    type_id: str,
    position_id: str,
    body: PositionUpdate,
    request: Request,
    auth: Auth,
    _: CanUpdateParish,
    db: TenantSession,
) -> TypeOut:
    t = service.get_type(db, type_id)
    p = _get_position(db, t, position_id)
    data = body.model_dump(exclude_unset=True)
    if "role_code" in data:
        p.role_id = service.resolve_role_for_position(db, data.pop("role_code"))
    for k, v in data.items():
        setattr(p, k, v)
    old, new = changes(p)
    record_audit(
        db,
        action="UPDATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit_position",
        entity_id=p.public_id,
        old=old,
        new=new,
    )
    db.expire(t)
    return _type_out(db, t)


@types_router.delete("/{type_id}/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(
    type_id: str, position_id: str, request: Request, auth: Auth, _: CanUpdateParish, db: TenantSession
) -> Response:
    t = service.get_type(db, type_id)
    p = _get_position(db, t, position_id)
    active = db.scalars(
        select(OrgUnitOfficeBearer.id).where(
            OrgUnitOfficeBearer.position_id == p.id, OrgUnitOfficeBearer.ended_at.is_(None)
        )
    ).first()
    if active is not None:
        raise Conflict("End the current terms for this position first", code="POSITION_IN_USE")
    p.soft_delete(auth.user.id)
    record_audit(
        db,
        action="DELETE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit_position",
        entity_id=p.public_id,
        old={"code": p.code},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================================ units
def _bearer_out(
    b: OrgUnitOfficeBearer,
    users: dict[int, User],
    roles: dict[int, Role],
    today: date,
    grants: dict[int, str],
) -> BearerOut:
    user = users.get(b.user_id) if b.user_id else None
    return BearerOut(
        id=b.public_id,
        position_code=b.position.code,
        position_name=b.position.name,
        user_id=user.public_id if user else None,
        holder_name=b.holder_name,
        valid_from=b.valid_from,
        valid_to=b.valid_to,
        current=b.is_current(today),
        ended_at=b.ended_at,
        grants_role=grants.get(b.id),
        remarks=b.remarks,
    )


def _bearers(db: Session, unit: OrgUnit, *, history: bool) -> list[BearerOut]:
    from app.modules.rbac.models import UserRoleAssignment

    stmt = select(OrgUnitOfficeBearer).where(OrgUnitOfficeBearer.org_unit_id == unit.id)
    if not history:
        stmt = service.current_bearers_stmt(unit.id)
    rows = list(db.scalars(stmt).unique())
    rows.sort(key=lambda b: (b.ended_at is not None, b.position.sort_order, b.valid_from))
    users = {
        u.id: u for u in db.scalars(select(User).where(User.id.in_({b.user_id for b in rows if b.user_id})))
    }
    roles = {r.id: r for r in db.scalars(select(Role))}
    grants: dict[int, str] = {}
    for b in rows:
        if b.role_assignment_id:
            a = db.get(UserRoleAssignment, b.role_assignment_id)
            if a is not None:
                grants[b.id] = roles[a.role_id].name
    return [_bearer_out(b, users, roles, date.today(), grants) for b in rows]


def _unit_out(db: Session, u: OrgUnit, auth: Auth) -> UnitOut:
    children = db.scalar(
        select(func.count())
        .select_from(OrgUnit)
        .where(OrgUnit.parent_id == u.id, OrgUnit.is_deleted.is_(False))
    )
    return UnitOut(
        id=u.public_id,
        code=u.code,
        name=u.name,
        name_local=u.name_local,
        type_code=u.type.code,
        type_name=u.type.name,
        parent=UnitBrief(id=u.parent.public_id, code=u.parent.code, name=u.parent.name)
        if u.parent and not u.parent.is_deleted
        else None,
        description=u.description,
        status=u.status,
        established_on=u.established_on,
        meeting_place=u.meeting_place,
        meeting_schedule=u.meeting_schedule,
        contact_phone=u.contact_phone,
        contact_email=u.contact_email,
        sub_unit_count=children or 0,
        office_bearers=_bearers(db, u, history=False),
        can_manage=auth.permissions.has("org_unit.manage_members", u.id),
        created_at=u.created_at,
    )


def _visible_unit(db: Session, unit_id: str, scope: PermissionScope) -> OrgUnit:
    u = service.get_unit(db, unit_id)
    if not scope.allows(u.id):
        raise NotFound()  # do not disclose units outside the caller's scope
    return u


def _parent(db: Session, parent_id: str | None) -> OrgUnit | None:
    if not parent_id:
        return None
    try:
        return service.get_unit(db, parent_id)
    except NotFound as exc:
        raise ValidationFailed(details=[{"field": "parent_id", "message": "Parent not found"}]) from exc


@units_router.get("", response_model=Page[UnitOut])
def list_units(
    auth: Auth,
    scope: CanView,
    db: TenantSession,
    params: PageQuery,
    type: Annotated[str | None, Query(max_length=30, description="Type code")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[str | None, Query(alias="status", pattern=r"^(ACTIVE|INACTIVE)$")] = None,
    parent: Annotated[str | None, Query(description="Parent unit public id; 'root' for top level")] = None,
) -> Page[UnitOut]:
    stmt = (
        select(OrgUnit)
        .join(OrgUnitType, OrgUnitType.id == OrgUnit.type_id)
        .where(OrgUnit.is_deleted.is_(False), scope.filter(OrgUnit.id))
    )
    if type:
        stmt = stmt.where(OrgUnitType.code == type.upper())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(OrgUnit.name.ilike(like), OrgUnit.code.ilike(like), OrgUnit.name_local.ilike(like))
        )
    if status_:
        stmt = stmt.where(OrgUnit.status == status_)
    if parent == "root":
        stmt = stmt.where(OrgUnit.parent_id.is_(None))
    elif parent:
        stmt = stmt.where(OrgUnit.parent_id == service.get_unit(db, parent).id)
    stmt = apply_sort(
        stmt,
        params.sort,
        {"name": OrgUnit.name, "code": OrgUnit.code, "created_at": OrgUnit.created_at},
        [OrgUnit.name, OrgUnit.id],
    )
    return paginate(db, stmt, params, lambda u: _unit_out(db, u, auth))


@units_router.post("", response_model=UnitOut, status_code=status.HTTP_201_CREATED)
def create_unit(body: UnitCreate, request: Request, auth: Auth, _: CanCreate, db: TenantSession) -> UnitOut:
    t = service.get_type(db, body.type_code)
    service.ensure_single_unit(db, t)
    parent = _parent(db, body.parent_id)
    service.validate_parent(db, None, parent)
    code = body.code or service.next_unit_code(db, t)
    if db.scalars(select(OrgUnit.id).where(OrgUnit.code == code)).first() is not None:
        raise Conflict(
            "An organisation with this code already exists",
            code="ORG_UNIT_CODE_EXISTS",
            details=[{"field": "code", "message": "Already in use"}],
        )
    data = body.model_dump(exclude={"type_code", "parent_id", "code"})
    u = OrgUnit(
        type_id=t.id, parent_id=parent.id if parent else None, code=code, created_by=auth.user.id, **data
    )
    db.add(u)
    db.flush()
    db.refresh(u)
    record_audit(
        db,
        action="CREATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit",
        entity_id=u.public_id,
        new={**body.model_dump(mode="json"), "code": code},
    )
    return _unit_out(db, u, auth)


@units_router.get("/mine", response_model=MyUnitsOut)
def my_units(
    auth: Auth,
    db: TenantSession,
    permission: Annotated[str, Query(max_length=80, description="e.g. activity.create")],
) -> MyUnitsOut:
    """Organisations the current user can act for with ``permission`` (for pickers in record forms)."""
    from app.modules.rbac.catalog import ALL_PERMISSIONS

    if permission not in ALL_PERMISSIONS:
        raise ValidationFailed(details=[{"field": "permission", "message": "Unknown permission"}])
    scope = auth.permissions.scope(permission)
    stmt = (
        select(OrgUnit)
        .join(OrgUnitType, OrgUnitType.id == OrgUnit.type_id)
        .where(OrgUnit.is_deleted.is_(False), OrgUnit.status == "ACTIVE", scope.filter(OrgUnit.id))
        .order_by(OrgUnitType.sort_order, OrgUnit.name)
    )
    return MyUnitsOut(
        parish=scope.parish_wide,
        units=[
            ScopedUnit(id=u.public_id, code=u.code, name=u.name, type_code=u.type.code, type_name=u.type.name)
            for u in db.scalars(stmt)
        ],
    )


@units_router.get("/{unit_id}", response_model=UnitOut)
def get_unit(unit_id: str, auth: Auth, scope: CanView, db: TenantSession) -> UnitOut:
    return _unit_out(db, _visible_unit(db, unit_id, scope), auth)


@units_router.patch("/{unit_id}", response_model=UnitOut)
def update_unit(
    unit_id: str, body: UnitUpdate, request: Request, auth: Auth, scope: CanUpdate, db: TenantSession
) -> UnitOut:
    u = _visible_unit(db, unit_id, scope)
    data = body.model_dump(exclude_unset=True, mode="json")
    if "parent_id" in data:
        if not scope.parish_wide:
            raise PermissionDenied("Only parish administrators can move organisations")
        parent = _parent(db, data.pop("parent_id"))
        service.validate_parent(db, u, parent)
        u.parent_id = parent.id if parent else None
    for k, v in body.model_dump(exclude_unset=True, exclude={"parent_id"}).items():
        setattr(u, k, v)
    old, new = changes(u)
    u.updated_by = auth.user.id
    record_audit(
        db,
        action="UPDATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit",
        entity_id=u.public_id,
        old=old,
        new=new,
    )
    db.flush()
    db.refresh(u)
    return _unit_out(db, u, auth)


def _set_status(unit_id: str, active: bool, request: Request, auth: Auth, db: Session) -> UnitOut:
    u = service.get_unit(db, unit_id)
    if active and u.parent is not None and u.parent.status != "ACTIVE":
        raise Conflict("Reactivate the parent organisation first", code="INVALID_STATE")
    if not active:
        active_children = db.scalars(
            select(OrgUnit.id).where(
                OrgUnit.parent_id == u.id, OrgUnit.status == "ACTIVE", OrgUnit.is_deleted.is_(False)
            )
        ).first()
        if active_children is not None:
            raise Conflict("Archive the sub-units first", code="HAS_ACTIVE_SUB_UNITS")
        ended = service.end_all_terms(db, u, auth.user.id)
    old = u.status
    u.status = "ACTIVE" if active else "INACTIVE"
    record_audit(
        db,
        action="ACTIVATE" if active else "ARCHIVE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit",
        entity_id=u.public_id,
        old={"status": old},
        new={"status": u.status},
        remarks=None if active else f"{ended} office term(s) ended",
    )
    return _unit_out(db, u, auth)


@units_router.post("/{unit_id}/archive", response_model=UnitOut)
def archive_unit(unit_id: str, request: Request, auth: Auth, _: CanDelete, db: TenantSession) -> UnitOut:
    """Deactivate an organisation (ends current office terms; history is kept)."""
    return _set_status(unit_id, False, request, auth, db)


@units_router.post("/{unit_id}/activate", response_model=UnitOut)
def activate_unit(unit_id: str, request: Request, auth: Auth, _: CanDelete, db: TenantSession) -> UnitOut:
    return _set_status(unit_id, True, request, auth, db)


@units_router.delete("/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(unit_id: str, request: Request, auth: Auth, _: CanDelete, db: TenantSession) -> Response:
    """Remove an organisation created by mistake (only when it has no history)."""
    u = service.get_unit(db, unit_id)
    if db.scalars(select(OrgUnit.id).where(OrgUnit.parent_id == u.id, OrgUnit.is_deleted.is_(False))).first():
        raise Conflict("Remove the sub-units first", code="HAS_SUB_UNITS")
    if db.scalars(select(OrgUnitOfficeBearer.id).where(OrgUnitOfficeBearer.org_unit_id == u.id)).first():
        raise Conflict("This organisation has office-bearer history; archive it instead", code="HAS_HISTORY")
    u.soft_delete(auth.user.id)
    record_audit(
        db,
        action="DELETE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit",
        entity_id=u.public_id,
        old={"code": u.code, "name": u.name},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- office bearers
@units_router.get("/{unit_id}/office-bearers", response_model=list[BearerOut])
def list_bearers(
    unit_id: str, scope: CanView, db: TenantSession, include_history: bool = False
) -> list[BearerOut]:
    return _bearers(db, _visible_unit(db, unit_id, scope), history=include_history)


@units_router.post("/{unit_id}/office-bearers", response_model=BearerOut, status_code=status.HTTP_201_CREATED)
def appoint(
    unit_id: str, body: BearerCreate, request: Request, auth: Auth, scope: CanManageMembers, db: TenantSession
) -> BearerOut:
    unit = _visible_unit(db, unit_id, scope)
    position = db.scalars(
        select(OrgUnitPosition).where(
            OrgUnitPosition.type_id == unit.type_id,
            OrgUnitPosition.code == body.position_code.upper(),
            OrgUnitPosition.is_deleted.is_(False),
        )
    ).first()
    if position is None:
        raise ValidationFailed(
            details=[{"field": "position_code", "message": "Unknown position for this type"}]
        )
    user = None
    if body.user_id:
        user = db.scalars(
            select(User).where(User.public_id == body.user_id, User.is_deleted.is_(False))
        ).first()
        if user is None:
            raise ValidationFailed(details=[{"field": "user_id", "message": "User not found"}])
    if user is not None and position.role_id is not None:
        role = db.get(Role, position.role_id)
        if user.id == auth.user.id:
            raise PermissionDenied(
                "You cannot appoint yourself to a position that grants a role", code="SELF_MODIFICATION"
            )
        if role is not None and role.scope_type == "PARISH" and not auth.permissions.has("user.assign_role"):
            raise PermissionDenied(
                f"Appointing a {position.name} grants the parish-wide role {role.name}",
                details=[{"field": "permission", "message": "user.assign_role"}],
            )
    member_id = None
    holder_name = body.holder_name
    if body.member_id:
        from app.modules.people.service import get_member  # avoid import cycle (people → org_units)

        member = get_member(db, body.member_id)
        member_id, holder_name = member.id, holder_name or member.full_name
    b = service.appoint(
        db,
        unit,
        position,
        user=user,
        holder_name=holder_name,
        member_id=member_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        actor_id=auth.user.id,
        remarks=body.remarks,
    )
    record_audit(
        db,
        action="OFFICE_BEARER_APPOINTED",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit",
        entity_id=unit.public_id,
        new={
            "position": position.code,
            "holder": b.holder_name,
            "user": body.user_id,
            "valid_from": b.valid_from,
            "valid_to": b.valid_to,
            "bearer": b.public_id,
        },
    )
    return next(x for x in _bearers(db, unit, history=True) if x.id == b.public_id)


@units_router.post("/{unit_id}/office-bearers/{bearer_id}/end", response_model=BearerOut)
def end_bearer(
    unit_id: str,
    bearer_id: str,
    body: BearerEnd,
    request: Request,
    auth: Auth,
    scope: CanManageMembers,
    db: TenantSession,
) -> BearerOut:
    unit = _visible_unit(db, unit_id, scope)
    b = db.scalars(
        select(OrgUnitOfficeBearer).where(
            OrgUnitOfficeBearer.public_id == bearer_id, OrgUnitOfficeBearer.org_unit_id == unit.id
        )
    ).first()
    if b is None:
        raise NotFound()
    service.end_term(db, b, end_date=body.end_date, actor_id=auth.user.id)
    record_audit(
        db,
        action="OFFICE_BEARER_ENDED",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="org_unit",
        entity_id=unit.public_id,
        old={"position": b.position.code, "holder": b.holder_name, "bearer": b.public_id},
        new={"valid_to": b.valid_to},
    )
    return next(x for x in _bearers(db, unit, history=True) if x.id == b.public_id)

"""Roles & permissions administration API (``/api/v1/roles``, ``/api/v1/permissions``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select

from app.common.audit import record_audit
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.modules.identity.deps import Auth
from app.modules.rbac.catalog import ADMIN_LOCKED_PERMISSIONS, ADMIN_ROLE, PERMISSION_CATALOG
from app.modules.rbac.deps import require_perm
from app.modules.rbac.models import Permission, Role, UserRoleAssignment
from app.modules.rbac.schemas import (
    PermissionModuleOut,
    PermissionOut,
    RoleCreate,
    RoleOut,
    RoleSummaryOut,
    RoleUpdate,
)
from app.modules.rbac.service import PermissionScope, assignment_active_clause
from app.tenancy.deps import TenantSession

router = APIRouter(tags=["roles"])

CanViewRoles = Annotated[PermissionScope, Depends(require_perm("role.view", parish_wide=True))]
CanManageRoles = Annotated[PermissionScope, Depends(require_perm("role.manage", parish_wide=True))]


def _active_users(db: TenantSession, role_id: int) -> int:
    stmt = select(func.count(func.distinct(UserRoleAssignment.user_id))).where(
        UserRoleAssignment.role_id == role_id, assignment_active_clause()
    )
    return db.scalar(stmt) or 0


def _role_out(db: TenantSession, role: Role, *, detail: bool = True) -> RoleOut | RoleSummaryOut:
    data = dict(
        id=role.public_id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        scope_type=role.scope_type,
        permission_count=len(role.permissions),
        active_users=_active_users(db, role.id),
    )
    if detail:
        return RoleOut(**data, permissions=sorted(p.code for p in role.permissions))
    return RoleSummaryOut(**data)


def _get_role(db: TenantSession, role_id: str) -> Role:
    role = db.scalars(select(Role).where(Role.public_id == role_id, Role.is_deleted.is_(False))).first()
    if role is None:
        raise NotFound()
    return role


def _permissions(db: TenantSession, codes: list[str]) -> list[Permission]:
    wanted = set(codes)
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(wanted))))
    unknown = wanted - {p.code for p in perms}
    if unknown:
        raise ValidationFailed(
            details=[{"field": "permissions", "message": f"Unknown permission: {c}"} for c in sorted(unknown)]
        )
    return perms


@router.get("/permissions", response_model=list[PermissionModuleOut])
def list_permissions(_: CanViewRoles, db: TenantSession) -> list[PermissionModuleOut]:
    perms = {p.code: p for p in db.scalars(select(Permission))}
    out = []
    for module, actions in PERMISSION_CATALOG.items():
        items = [
            PermissionOut(code=p.code, module=p.module, action=p.action, description=p.description)
            for a in actions
            if (p := perms.get(f"{module}.{a}")) is not None
        ]
        out.append(PermissionModuleOut(module=module, permissions=items))
    return out


@router.get("/roles", response_model=list[RoleSummaryOut])
def list_roles(_: CanViewRoles, db: TenantSession) -> list[RoleSummaryOut]:
    roles = db.scalars(
        select(Role).where(Role.is_deleted.is_(False)).order_by(Role.is_system.desc(), Role.name)
    )
    return [_role_out(db, r, detail=False) for r in roles]  # type: ignore[misc]


@router.get("/roles/{role_id}", response_model=RoleOut)
def get_role(role_id: str, _: CanViewRoles, db: TenantSession) -> RoleOut | RoleSummaryOut:
    return _role_out(db, _get_role(db, role_id))


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate, request: Request, auth: Auth, _: CanManageRoles, db: TenantSession):  # type: ignore[no-untyped-def]
    code = body.code.upper()
    if db.scalars(select(Role.id).where(Role.code == code)).first() is not None:
        raise Conflict("A role with this code already exists", code="ROLE_CODE_EXISTS")
    role = Role(
        code=code,
        name=body.name,
        description=body.description,
        scope_type=body.scope_type,
        is_system=False,
        created_by=auth.user.id,
    )
    role.permissions = _permissions(db, body.permissions)
    db.add(role)
    db.flush()
    record_audit(
        db,
        action="CREATE",
        module="roles",
        user_id=auth.user.id,
        request=request,
        entity_type="role",
        entity_id=role.public_id,
        new={**body.model_dump(), "code": code},
    )
    return _role_out(db, role)


@router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: str, body: RoleUpdate, request: Request, auth: Auth, _: CanManageRoles, db: TenantSession
):  # type: ignore[no-untyped-def]
    role = _get_role(db, role_id)
    old = {
        "name": role.name,
        "description": role.description,
        "permissions": sorted(p.code for p in role.permissions),
    }
    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.permissions is not None:
        perms = _permissions(db, body.permissions)
        if role.code == ADMIN_ROLE:
            missing = ADMIN_LOCKED_PERMISSIONS - {p.code for p in perms}
            if missing:
                raise ValidationFailed(
                    "The Parish Administrator role must keep user and role management permissions",
                    code="ADMIN_PERMISSIONS_LOCKED",
                    details=[{"field": "permissions", "message": f"Required: {c}"} for c in sorted(missing)],
                )
        role.permissions = perms
    role.updated_by = auth.user.id
    record_audit(
        db,
        action="UPDATE",
        module="roles",
        user_id=auth.user.id,
        request=request,
        entity_type="role",
        entity_id=role.public_id,
        old=old,
        new=body.model_dump(exclude_unset=True),
    )
    return _role_out(db, role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: str, request: Request, auth: Auth, _: CanManageRoles, db: TenantSession) -> Response:
    role = _get_role(db, role_id)
    if role.is_system:
        raise Conflict("System roles cannot be deleted", code="SYSTEM_ROLE")
    if _active_users(db, role.id):
        raise Conflict("Remove this role from all users first", code="ROLE_IN_USE")
    role.soft_delete(auth.user.id)
    record_audit(
        db,
        action="DELETE",
        module="roles",
        user_id=auth.user.id,
        request=request,
        entity_type="role",
        entity_id=role.public_id,
        old={"code": role.code},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""User administration API (``/api/v1/users``).

Guards:
* administrators cannot change their own roles, status or deletion state (no self-escalation/lock-out);
* the last active Parish Administrator cannot be deactivated, deleted or lose that role;
* every change is audited.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.audit import record_audit
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.db.base import utcnow
from app.modules.identity import service as identity
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.rbac.catalog import ADMIN_ROLE
from app.modules.rbac.deps import require_any, require_perm
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.rbac.schemas import AssignmentCreate, AssignmentOut
from app.modules.rbac.service import (
    PermissionScope,
    assign_role,
    assignment_active_clause,
    ensure_not_last_admin,
    org_unit_public_id,
    org_units_available,
    resolve_org_unit,
    role_by_code,
)
from app.modules.users.schemas import UserCreate, UserOut, UserUpdate
from app.tenancy.deps import TenantSession

router = APIRouter(prefix="/users", tags=["users"])
MODULE = "users"


def _perm(code: str):  # type: ignore[no-untyped-def]
    return Annotated[PermissionScope, Depends(require_perm(code, parish_wide=True))]


CanView = _perm("user.view")
CanCreate = _perm("user.create")
CanUpdate = _perm("user.update")
CanDelete = _perm("user.delete")
CanAssign = _perm("user.assign_role")


# ----------------------------------------------------------------------------- helpers
def _roles_by_user(db: Session, user_ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = defaultdict(list)
    if not user_ids:
        return out
    rows = db.execute(
        select(UserRoleAssignment.user_id, Role.code)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(
            UserRoleAssignment.user_id.in_(user_ids), assignment_active_clause(), Role.is_deleted.is_(False)
        )
    )
    for uid, code in rows:
        if code not in out[uid]:
            out[uid].append(code)
    return out


def _user_out(u: User, roles: list[str]) -> UserOut:
    return UserOut(
        id=u.public_id,
        username=u.username,
        full_name=u.full_name,
        email=u.email,
        phone=u.phone,
        preferred_language=u.preferred_language,
        is_active=u.is_active,
        is_locked=bool(u.locked_until and u.locked_until > utcnow()),
        must_change_password=u.must_change_password,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
        roles=sorted(roles),
    )


def _one_out(db: Session, u: User) -> UserOut:
    return _user_out(u, _roles_by_user(db, [u.id]).get(u.id, []))


def _get_user(db: Session, user_id: str) -> User:
    u = db.scalars(select(User).where(User.public_id == user_id, User.is_deleted.is_(False))).first()
    if u is None:
        raise NotFound()
    return u


def _not_self(auth: Auth, user: User, what: str) -> None:
    if user.id == auth.user.id:
        raise PermissionDenied(f"You cannot {what} your own account", code="SELF_MODIFICATION")


def _assignment_out(db: Session, a: UserRoleAssignment) -> AssignmentOut:
    from datetime import date

    return AssignmentOut(
        id=a.public_id,
        role_code=a.role.code,
        role_name=a.role.name,
        org_unit_id=org_unit_public_id(db, a.org_unit_id),
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        active=a.is_active_on(date.today()),
        created_at=a.created_at,
        ended_at=a.ended_at,
        remarks=a.remarks,
    )


def _assign(
    db: Session, auth: Auth, user: User, body: AssignmentCreate, request: Request
) -> UserRoleAssignment:
    role = role_by_code(db, body.role_code)
    if role is None:
        raise ValidationFailed(details=[{"field": "role_code", "message": "Unknown role"}])
    org_unit_id = None
    if body.org_unit_id:
        if not org_units_available():
            raise ValidationFailed(
                "Organisation-scoped roles become available with the organisation module",
                code="ORG_UNITS_NOT_AVAILABLE",
            )
        org_unit_id = resolve_org_unit(db, body.org_unit_id)
        if org_unit_id is None:
            raise ValidationFailed(details=[{"field": "org_unit_id", "message": "Organisation not found"}])
    a = assign_role(
        db,
        user,
        role,
        org_unit_id=org_unit_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        assigned_by=auth.user.id,
        remarks=body.remarks,
    )
    record_audit(
        db,
        action="ROLE_ASSIGNED",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
        new={
            "role": role.code,
            "org_unit_id": body.org_unit_id,
            "valid_from": a.valid_from,
            "valid_to": a.valid_to,
            "assignment": a.public_id,
        },
    )
    return a


# ----------------------------------------------------------------------------- lookup
class UserLookupOut(BaseModel):
    id: str
    username: str
    full_name: str


# Anyone who assigns people in forms: office bearers, action items, delegations of approvals.
LOOKUP_PERMISSIONS = (
    "user.view",
    "org_unit.manage_members",
    "action_item.create",
    "action_item.update",
    "activity.review",
    "activity.approve",
    "meeting.review",
    "meeting.approve",
    "finance.review",
    "finance.approve",
    "notice.review",
    "notice.approve",
    "finance_period.approve",
    "workflow.manage",
)


@router.get("/lookup", response_model=list[UserLookupOut])
def lookup_users(
    _: Annotated[list[PermissionScope], Depends(require_any(*LOOKUP_PERMISSIONS))],
    db: TenantSession,
    q: Annotated[str, Query(min_length=2, max_length=100)],
) -> list[UserLookupOut]:
    """Minimal active-user search for pickers (e.g. appointing office bearers). Names only."""
    like = f"%{q.strip()}%"
    rows = db.scalars(
        select(User)
        .where(
            User.is_deleted.is_(False),
            User.is_active.is_(True),
            or_(User.username.ilike(like), User.full_name.ilike(like)),
        )
        .order_by(User.full_name)
        .limit(20)
    )
    return [UserLookupOut(id=u.public_id, username=u.username, full_name=u.full_name) for u in rows]


# ----------------------------------------------------------------------------- users
@router.get("", response_model=Page[UserOut])
def list_users(
    _: CanView,
    db: TenantSession,
    params: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
    role: Annotated[str | None, Query(max_length=50, description="Role code")] = None,
) -> Page[UserOut]:
    stmt = select(User).where(User.is_deleted.is_(False))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.full_name.ilike(like), User.email.ilike(like)))
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if role:
        stmt = stmt.where(
            User.id.in_(
                select(UserRoleAssignment.user_id)
                .join(Role, Role.id == UserRoleAssignment.role_id)
                .where(Role.code == role.upper(), assignment_active_clause())
            )
        )
    stmt = apply_sort(
        stmt,
        params.sort,
        {
            "username": User.username,
            "full_name": User.full_name,
            "last_login_at": User.last_login_at,
            "created_at": User.created_at,
        },
        [User.full_name, User.id],
    )
    page = paginate(db, stmt, params, lambda u: u)
    roles = _roles_by_user(db, [u.id for u in page.items])
    return Page[UserOut](
        items=[_user_out(u, roles.get(u.id, [])) for u in page.items],
        page=page.page,
        size=page.size,
        total=page.total,
        pages=page.pages,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request, auth: Auth, _: CanCreate, db: TenantSession) -> UserOut:
    if body.role_codes and not auth.permissions.has("user.assign_role"):
        raise PermissionDenied(details=[{"field": "permission", "message": "user.assign_role"}])
    invite = not body.password
    password = body.password or (identity.generate_token(18) + "-Aa1")
    user = identity.create_user(
        db,
        username=body.username,
        full_name=body.full_name,
        email=str(body.email) if body.email else None,
        phone=body.phone,
        password=password,
        must_change_password=True,
        actor_id=auth.user.id,
        enforce_policy=not invite,
    )
    user.preferred_language = body.preferred_language
    record_audit(
        db,
        action="CREATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
        new=body.model_dump(mode="json"),
    )
    for code in dict.fromkeys(c.upper() for c in body.role_codes):
        _assign(db, auth, user, AssignmentCreate(role_code=code), request)
    if invite:
        identity.send_reset_link(db, auth.tenant, user, request, invite=True)
    return _one_out(db, user)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, _: CanView, db: TenantSession) -> UserOut:
    return _one_out(db, _get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str, body: UserUpdate, request: Request, auth: Auth, _: CanUpdate, db: TenantSession
) -> UserOut:
    user = _get_user(db, user_id)
    changes = body.model_dump(exclude_unset=True, mode="json")
    if changes.get("email"):
        changes["email"] = changes["email"].lower()
        clash = db.scalars(select(User.id).where(User.email == changes["email"], User.id != user.id)).first()
        if clash is not None:
            raise Conflict("Email already in use", code="EMAIL_EXISTS")
    old = {k: getattr(user, k) for k in changes}
    for k, v in changes.items():
        setattr(user, k, v)
    user.updated_by = auth.user.id
    record_audit(
        db,
        action="UPDATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
        old=old,
        new=changes,
    )
    return _one_out(db, user)


def _set_active(user_id: str, active: bool, request: Request, auth: Auth, db: Session) -> UserOut:
    user = _get_user(db, user_id)
    _not_self(auth, user, "deactivate" if not active else "reactivate")
    if user.is_active == active:
        return _one_out(db, user)
    if not active:
        ensure_not_last_admin(db, excluding_user=user.id)
        identity.revoke_all_sessions(db, user.id, "USER_DEACTIVATED")
    user.is_active = active
    user.updated_by = auth.user.id
    record_audit(
        db,
        action="ACTIVATE" if active else "DEACTIVATE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
    )
    return _one_out(db, user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: str, request: Request, auth: Auth, _: CanUpdate, db: TenantSession) -> UserOut:
    return _set_active(user_id, False, request, auth, db)


@router.post("/{user_id}/activate", response_model=UserOut)
def activate_user(user_id: str, request: Request, auth: Auth, _: CanUpdate, db: TenantSession) -> UserOut:
    return _set_active(user_id, True, request, auth, db)


@router.post("/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: str, request: Request, auth: Auth, _: CanUpdate, db: TenantSession) -> UserOut:
    user = _get_user(db, user_id)
    user.locked_until = None
    user.failed_login_count = 0
    record_audit(
        db,
        action="UNLOCK",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
    )
    return _one_out(db, user)


@router.post("/{user_id}/send-password-reset", status_code=status.HTTP_202_ACCEPTED)
def send_password_reset(
    user_id: str, request: Request, auth: Auth, _: CanUpdate, db: TenantSession
) -> dict[str, str]:
    user = _get_user(db, user_id)
    if not user.email:
        raise ValidationFailed("This user has no email address", code="NO_EMAIL")
    identity.send_reset_link(db, auth.tenant, user, request)
    return {"message": f"A password reset link was sent to {user.email}"}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, request: Request, auth: Auth, _: CanDelete, db: TenantSession) -> Response:
    """Archive the account (soft delete): sessions revoked, role assignments ended, history kept."""
    user = _get_user(db, user_id)
    _not_self(auth, user, "delete")
    ensure_not_last_admin(db, excluding_user=user.id)
    identity.revoke_all_sessions(db, user.id, "USER_DELETED")
    now = utcnow()
    for a in db.scalars(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user.id, UserRoleAssignment.ended_at.is_(None)
        )
    ):
        a.ended_at, a.ended_by = now, auth.user.id
    user.is_active = False
    user.soft_delete(auth.user.id)
    record_audit(
        db,
        action="DELETE",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
        old={"username": user.username},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- role assignments
@router.get("/{user_id}/roles", response_model=list[AssignmentOut])
def list_user_roles(
    user_id: str, _: CanView, db: TenantSession, include_history: bool = False
) -> list[AssignmentOut]:
    user = _get_user(db, user_id)
    stmt = select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id)
    if not include_history:
        stmt = stmt.where(UserRoleAssignment.ended_at.is_(None))
    rows = db.scalars(stmt.order_by(UserRoleAssignment.created_at.desc())).unique()
    return [_assignment_out(db, a) for a in rows]


@router.post("/{user_id}/roles", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def add_user_role(
    user_id: str, body: AssignmentCreate, request: Request, auth: Auth, _: CanAssign, db: TenantSession
) -> AssignmentOut:
    user = _get_user(db, user_id)
    _not_self(auth, user, "change roles of")
    return _assignment_out(db, _assign(db, auth, user, body, request))


@router.delete("/{user_id}/roles/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def end_user_role(
    user_id: str, assignment_id: str, request: Request, auth: Auth, _: CanAssign, db: TenantSession
) -> Response:
    """End a role assignment (kept as history)."""
    user = _get_user(db, user_id)
    _not_self(auth, user, "change roles of")
    a = db.scalars(
        select(UserRoleAssignment).where(
            UserRoleAssignment.public_id == assignment_id, UserRoleAssignment.user_id == user.id
        )
    ).first()
    if a is None or a.ended_at is not None:
        raise NotFound()
    if a.role.code == ADMIN_ROLE and a.org_unit_id is None:
        ensure_not_last_admin(db, excluding_assignment=a.id)
    a.ended_at, a.ended_by = utcnow(), auth.user.id
    record_audit(
        db,
        action="ROLE_REMOVED",
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
        old={"role": a.role.code, "assignment": a.public_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

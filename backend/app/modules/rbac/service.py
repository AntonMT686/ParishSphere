"""RBAC: seeding, effective permission resolution and scope checks.

Effective permissions are computed per request from the user's *active* assignments:

* a parish-wide assignment grants the role's permissions everywhere;
* an org-unit assignment grants them only for records belonging to that organisation unit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, false, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import Conflict, PermissionDenied
from app.modules.identity.models import User
from app.modules.rbac.catalog import (
    ADMIN_ROLE,
    PERMISSION_CATALOG,
    SYSTEM_ROLES,
)
from app.modules.rbac.models import Permission, Role, UserRoleAssignment, role_permissions
from app.tenancy.seed import register_seeder


# ----------------------------------------------------------------------------- scope
@dataclass(frozen=True)
class PermissionScope:
    """Where a permission applies for the current user."""

    code: str
    parish_wide: bool = False
    org_unit_ids: frozenset[int] = field(default_factory=frozenset)

    @property
    def granted(self) -> bool:
        return self.parish_wide or bool(self.org_unit_ids)

    def allows(self, org_unit_id: int | None) -> bool:
        """Parish-level records (``org_unit_id`` None) require a parish-wide grant."""
        if self.parish_wide:
            return True
        return org_unit_id is not None and org_unit_id in self.org_unit_ids

    def filter(self, column: Any) -> ColumnElement[bool]:
        """SQL filter restricting a query on ``column`` (an org_unit_id column) to this scope."""
        if self.parish_wide:
            return true()
        if not self.org_unit_ids:
            return false()
        return column.in_(self.org_unit_ids)


@dataclass
class EffectivePermissions:
    parish_wide: set[str] = field(default_factory=set)
    by_org_unit: dict[str, set[int]] = field(default_factory=dict)
    role_codes: set[str] = field(default_factory=set)

    def scope(self, code: str) -> PermissionScope:
        return PermissionScope(
            code=code,
            parish_wide=code in self.parish_wide,
            org_unit_ids=frozenset(self.by_org_unit.get(code, set())),
        )

    def has(self, code: str, org_unit_id: int | None = None, *, anywhere: bool = False) -> bool:
        s = self.scope(code)
        return s.granted if anywhere else s.allows(org_unit_id)

    @property
    def all_codes(self) -> set[str]:
        return self.parish_wide | set(self.by_org_unit)


def assignment_active_clause(today: date | None = None) -> ColumnElement[bool]:
    today = today or date.today()
    return and_(
        UserRoleAssignment.ended_at.is_(None),
        UserRoleAssignment.valid_from <= today,
        or_(UserRoleAssignment.valid_to.is_(None), UserRoleAssignment.valid_to >= today),
    )


def active_assignments_stmt(user_id: int, today: date | None = None) -> Select[tuple[UserRoleAssignment]]:
    return select(UserRoleAssignment).where(
        UserRoleAssignment.user_id == user_id, assignment_active_clause(today)
    )


def effective_permissions(session: Session, user: User, today: date | None = None) -> EffectivePermissions:
    eff = EffectivePermissions()
    if not user.is_active or user.is_deleted:
        return eff
    for a in session.scalars(active_assignments_stmt(user.id, today)).unique():
        role = a.role
        if role.is_deleted:
            continue
        eff.role_codes.add(role.code)
        codes = {p.code for p in role.permissions}
        if a.org_unit_id is None:
            eff.parish_wide |= codes
        else:
            for c in codes:
                eff.by_org_unit.setdefault(c, set()).add(a.org_unit_id)
    # A role held for an organisation also applies to its sub-units (e.g. Anbiyam zone → groups).
    if eff.by_org_unit and _org_unit_descendants is not None:
        roots = set().union(*eff.by_org_unit.values())
        tree = _org_unit_descendants(session, roots)
        for c, ids in eff.by_org_unit.items():
            eff.by_org_unit[c] = set().union(*(tree.get(i, {i}) for i in ids))
    return eff


def assert_permission(eff: EffectivePermissions, code: str, org_unit_id: int | None = None) -> None:
    if not eff.has(code, org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": code}])


# ----------------------------------------------------------------------------- org unit resolver
# The organisation module (T7) registers a resolver mapping an org unit public id → (id, exists).
OrgUnitResolver = Callable[[Session, str], int | None]
OrgUnitPublicId = Callable[[Session, int], str | None]
OrgUnitTree = Callable[[Session, set[int]], dict[int, set[int]]]
_org_unit_resolver: OrgUnitResolver | None = None
_org_unit_public_id: OrgUnitPublicId | None = None
_org_unit_descendants: OrgUnitTree | None = None
_org_unit_ancestors: OrgUnitTree | None = None


def register_org_unit_resolver(
    resolve: OrgUnitResolver,
    public_id: OrgUnitPublicId,
    descendants: OrgUnitTree | None = None,
    ancestors: OrgUnitTree | None = None,
) -> None:
    """Called by the organisation module so RBAC can address and traverse organisation units.

    ``descendants``/``ancestors`` map each given unit id to itself plus all sub-/parent units.
    """
    global _org_unit_resolver, _org_unit_public_id, _org_unit_descendants, _org_unit_ancestors
    _org_unit_resolver, _org_unit_public_id = resolve, public_id
    _org_unit_descendants, _org_unit_ancestors = descendants, ancestors


def org_unit_public_id(session: Session, org_unit_id: int | None) -> str | None:
    if org_unit_id is None or _org_unit_public_id is None:
        return None
    return _org_unit_public_id(session, org_unit_id)


def resolve_org_unit(session: Session, public_id: str) -> int | None:
    if _org_unit_resolver is None:
        return None
    return _org_unit_resolver(session, public_id)


def org_units_available() -> bool:
    return _org_unit_resolver is not None


# ----------------------------------------------------------------------------- admin guard
def count_active_admins(
    session: Session, *, excluding_user: int | None = None, excluding_assignment: int | None = None
) -> int:
    """Active users holding a parish-wide PARISH_ADMIN assignment today."""
    today = date.today()
    stmt = (
        select(UserRoleAssignment.user_id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .join(User, User.id == UserRoleAssignment.user_id)
        .where(
            Role.code == ADMIN_ROLE,
            UserRoleAssignment.org_unit_id.is_(None),
            assignment_active_clause(today),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if excluding_user is not None:
        stmt = stmt.where(UserRoleAssignment.user_id != excluding_user)
    if excluding_assignment is not None:
        stmt = stmt.where(UserRoleAssignment.id != excluding_assignment)
    return len(set(session.scalars(stmt)))


def ensure_not_last_admin(session: Session, **kwargs: int | None) -> None:
    """Refuse a change that would take the parish from ≥1 active administrator to none."""
    if count_active_admins(session) > 0 and count_active_admins(session, **kwargs) == 0:
        raise Conflict("At least one active Parish Administrator must remain", code="LAST_ADMIN")


# ----------------------------------------------------------------------------- assignment
def assign_role(
    session: Session,
    user: User,
    role: Role,
    *,
    org_unit_id: int | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    assigned_by: int | None = None,
    remarks: str | None = None,
) -> UserRoleAssignment:
    from app.core.errors import ValidationFailed

    if role.scope_type == "PARISH" and org_unit_id is not None:
        raise ValidationFailed(
            f"{role.name} is a parish-wide role",
            details=[{"field": "org_unit_id", "message": "Must be empty for this role"}],
        )
    if role.scope_type == "ORG_UNIT" and org_unit_id is None:
        raise ValidationFailed(
            f"{role.name} must be assigned for a specific organisation",
            details=[{"field": "org_unit_id", "message": "Required for this role"}],
        )
    valid_from = valid_from or date.today()
    if valid_to is not None and valid_to < valid_from:
        raise ValidationFailed(details=[{"field": "valid_to", "message": "Must be on or after valid_from"}])
    duplicate = session.scalars(
        active_assignments_stmt(user.id).where(
            UserRoleAssignment.role_id == role.id,
            UserRoleAssignment.org_unit_id.is_(None)
            if org_unit_id is None
            else UserRoleAssignment.org_unit_id == org_unit_id,
        )
    ).first()
    if duplicate is not None:
        raise Conflict("The user already holds this role", code="ROLE_ALREADY_ASSIGNED")
    a = UserRoleAssignment(
        user_id=user.id,
        role_id=role.id,
        org_unit_id=org_unit_id,
        valid_from=valid_from,
        valid_to=valid_to,
        assigned_by=assigned_by,
        remarks=remarks,
    )
    session.add(a)
    session.flush()
    return a


def role_by_code(session: Session, code: str) -> Role | None:
    return session.scalars(select(Role).where(Role.code == code.upper(), Role.is_deleted.is_(False))).first()


# ----------------------------------------------------------------------------- seeding
@register_seeder("rbac.catalog", order=20)
def seed_rbac(session: Session, _: dict[str, Any]) -> None:
    """Sync the permission catalog and system roles (idempotent; preserves admin customisations)."""
    existing = {p.code: p for p in session.scalars(select(Permission))}
    new_codes: set[str] = set()
    for module, actions in PERMISSION_CATALOG.items():
        for action, description in actions.items():
            code = f"{module}.{action}"
            if code not in existing:
                perm = Permission(code=code, module=module, action=action, description=description)
                session.add(perm)
                existing[code] = perm
                new_codes.add(code)
            elif existing[code].description != description:
                existing[code].description = description
    session.flush()

    for rd in SYSTEM_ROLES:
        role = session.scalars(select(Role).where(Role.code == rd.code)).first()
        if role is None:
            role = Role(
                code=rd.code,
                name=rd.name,
                description=rd.description,
                is_system=True,
                scope_type=rd.scope_type,
            )
            role.permissions = [existing[c] for c in sorted(rd.permissions)]
            session.add(role)
        else:
            # Grant only permissions introduced by this release; keep the parish's own edits.
            have = {p.code for p in role.permissions}
            role.permissions.extend(existing[c] for c in sorted(rd.permissions & new_codes - have))


# ----------------------------------------------------------------------------- recipients
def users_with_permission(
    session: Session, code: str, org_unit_id: int | None = None, *, role_code: str | None = None
) -> list[User]:
    """Active users holding ``code`` for ``org_unit_id`` (parish-wide holders always qualify).

    Used to find reviewers/approvers and notification recipients.
    """
    stmt = (
        select(User)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .join(role_permissions, role_permissions.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(
            Permission.code == code,
            Role.is_deleted.is_(False),
            assignment_active_clause(),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if org_unit_id is None:
        stmt = stmt.where(UserRoleAssignment.org_unit_id.is_(None))
    else:
        # Holders for this unit or any parent unit qualify (roles flow down the tree).
        units = (
            _org_unit_ancestors(session, {org_unit_id}).get(org_unit_id, {org_unit_id})
            if _org_unit_ancestors is not None
            else {org_unit_id}
        )
        stmt = stmt.where(
            or_(UserRoleAssignment.org_unit_id.is_(None), UserRoleAssignment.org_unit_id.in_(units))
        )
    if role_code is not None:
        stmt = stmt.where(Role.code == role_code)
    return list(session.scalars(stmt.distinct()).unique())

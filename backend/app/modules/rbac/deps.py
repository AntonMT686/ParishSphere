"""Authorization dependencies.

Usage::

    @router.get("/families")
    def list_families(scope: Annotated[PermissionScope, Depends(require_perm("family.view"))]): ...

``require_perm`` passes when the user holds the permission anywhere (parish-wide or for at least one
organisation unit) and returns the :class:`PermissionScope` so repositories can filter rows
(``scope.filter(Model.org_unit_id)``) and services can check single records (``scope.allows(id)``).
All checks are enforced here, on the backend — never only in the UI.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.errors import PermissionDenied
from app.modules.identity.deps import Auth
from app.modules.rbac.catalog import ALL_PERMISSIONS
from app.modules.rbac.service import PermissionScope


def require_perm(code: str, *, parish_wide: bool = False) -> Callable[[Auth], PermissionScope]:
    if code not in ALL_PERMISSIONS:
        raise ValueError(f"Unknown permission {code!r}")

    def dependency(auth: Auth) -> PermissionScope:
        scope = auth.permissions.scope(code)
        if not scope.granted or (parish_wide and not scope.parish_wide):
            raise PermissionDenied(details=[{"field": "permission", "message": code}])
        return scope

    dependency.__name__ = f"require_{code.replace('.', '_')}"
    return dependency


def require_any(*codes: str) -> Callable[[Auth], list[PermissionScope]]:
    for c in codes:
        if c not in ALL_PERMISSIONS:
            raise ValueError(f"Unknown permission {c!r}")

    def dependency(auth: Auth) -> list[PermissionScope]:
        scopes = [auth.permissions.scope(c) for c in codes]
        if not any(s.granted for s in scopes):
            raise PermissionDenied(details=[{"field": "permission", "message": " | ".join(codes)}])
        return scopes

    return dependency

"""Authentication dependencies for parish (tenant) routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import set_user_id
from app.core.errors import AppError, NotAuthenticated
from app.core.security import decode_access_token
from app.db.tenant import TenantDescriptor
from app.modules.identity.models import User, UserSession
from app.modules.identity.service import SessionExpired, check_session_alive, touch_session
from app.tenancy.deps import CurrentTenant, TenantSession

if TYPE_CHECKING:
    from app.modules.rbac.service import EffectivePermissions

bearer = HTTPBearer(auto_error=False)


class TenantMismatch(AppError):
    status_code = 403
    code = "TENANT_MISMATCH"
    message = "This token was not issued for this parish"


@dataclass
class AuthContext:
    user: User
    session: UserSession
    tenant: TenantDescriptor
    db: Session
    _permissions: EffectivePermissions | None = None

    @property
    def permissions(self) -> EffectivePermissions:
        """Effective permissions, resolved once per request."""
        if self._permissions is None:
            from app.modules.rbac.service import effective_permissions

            self._permissions = effective_permissions(self.db, self.user)
        return self._permissions


def get_auth_context(
    request: Request,
    tenant: CurrentTenant,
    db: TenantSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthContext:
    if credentials is None:
        raise NotAuthenticated()
    claims = decode_access_token(credentials.credentials)
    if claims.get("typ") != "tenant":
        raise NotAuthenticated("Parish credentials required", code="INVALID_TOKEN_TYPE")
    if claims.get("tid") != tenant.public_id:
        raise TenantMismatch()
    sess = db.scalars(select(UserSession).where(UserSession.public_id == claims.get("sid"))).first()
    if sess is None:
        raise NotAuthenticated("Session not found", code="SESSION_REVOKED")
    try:
        check_session_alive(sess)
    except SessionExpired:
        db.commit()  # persist idle/expiry revocation before the error rolls the request back
        raise
    user = sess.user
    if user.public_id != claims["sub"] or not user.is_active or user.is_deleted:
        raise NotAuthenticated()
    touch_session(sess)
    set_user_id(user.public_id)
    request.state.user = user
    ctx = AuthContext(user=user, session=sess, tenant=tenant, db=db)
    request.state.auth = ctx
    return ctx


Auth = Annotated[AuthContext, Depends(get_auth_context)]


def get_current_user(ctx: Auth) -> User:
    return ctx.user


CurrentUser = Annotated[User, Depends(get_current_user)]

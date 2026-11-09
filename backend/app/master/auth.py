"""Platform-user (super admin / diocese admin) authentication.

Platform tokens (``typ=platform``) are only accepted on ``/api/v1/platform/*`` routes and never
grant access to parish data. Refresh-token sessions are added in T3.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import set_user_id
from app.core.errors import AppError, NotAuthenticated, PermissionDenied
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.db.base import utcnow
from app.db.master import get_master_session
from app.master.models import DioceseUserScope, PlatformAuditLog, PlatformUser

bearer = HTTPBearer(auto_error=False)

MasterSession = Annotated[Session, Depends(get_master_session)]


class InvalidCredentials(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    message = "Invalid email or password"


class AccountLocked(AppError):
    status_code = 403
    code = "ACCOUNT_LOCKED"
    message = "Account temporarily locked after repeated failed logins"


def _client_ip(request: Request | None) -> str | None:
    return request.client.host if request is not None and request.client else None


def authenticate_platform_user(
    session: Session, email: str, password: str, request: Request | None = None
) -> PlatformUser:
    settings = get_settings()
    user = session.scalars(
        select(PlatformUser).where(PlatformUser.email == email.lower(), PlatformUser.is_deleted.is_(False))
    ).first()
    now = utcnow()
    if user is None:
        verify_password(hash_password("timing-equaliser"), password)  # mitigate user enumeration timing
        raise InvalidCredentials()
    if user.locked_until and user.locked_until > now:
        raise AccountLocked()
    if not user.is_active or not verify_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_count = 0
        session.add(PlatformAuditLog(actor_id=user.id, action="LOGIN_FAILED", ip=_client_ip(request)))
        session.commit()  # persist the failure even though we raise
        raise InvalidCredentials()
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session.add(PlatformAuditLog(actor_id=user.id, action="LOGIN", ip=_client_ip(request)))
    return user


def issue_platform_token(user: PlatformUser) -> tuple[str, int]:
    ttl = get_settings().access_token_ttl_minutes
    return create_access_token(subject=user.public_id, token_type="platform", ttl_minutes=ttl), ttl * 60


def get_current_platform_user(
    session: MasterSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> PlatformUser:
    if credentials is None:
        raise NotAuthenticated()
    claims = decode_access_token(credentials.credentials)
    if claims.get("typ") != "platform":
        raise NotAuthenticated("Platform credentials required", code="INVALID_TOKEN_TYPE")
    user = session.scalars(
        select(PlatformUser).where(
            PlatformUser.public_id == claims["sub"], PlatformUser.is_deleted.is_(False)
        )
    ).first()
    if user is None or not user.is_active:
        raise NotAuthenticated()
    set_user_id(user.public_id)
    return user


CurrentPlatformUser = Annotated[PlatformUser, Depends(get_current_platform_user)]


def require_super_admin(user: CurrentPlatformUser) -> PlatformUser:
    if not user.is_super_admin:
        raise PermissionDenied()
    return user


SuperAdmin = Annotated[PlatformUser, Depends(require_super_admin)]


def allowed_diocese_ids(session: Session, user: PlatformUser) -> set[int] | None:
    """None means unrestricted (super admin)."""
    if user.is_super_admin:
        return None
    return set(
        session.scalars(
            select(DioceseUserScope.diocese_id).where(DioceseUserScope.platform_user_id == user.id)
        )
    )


def create_platform_user(
    session: Session, *, email: str, full_name: str, password: str, is_super_admin: bool = False
) -> PlatformUser:
    user = PlatformUser(
        email=email.lower(),
        full_name=full_name,
        password_hash=hash_password(password),
        is_super_admin=is_super_admin,
    )
    session.add(user)
    session.flush()
    return user

"""Parish-user authentication & session lifecycle (docs/06-security.md).

* Login issues a 15-minute access JWT (``typ=tenant``, ``tid``, ``sid``) and an opaque refresh token.
* Refresh tokens are single-use and rotated; presenting a used token revokes the whole session.
* Sessions expire after ``idle_timeout_minutes`` of inactivity and after an absolute lifetime.
* Accounts lock after ``max_failed_logins`` failures; client IPs are throttled across usernames.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.common.audit import client_ip, record_audit
from app.common.email import send_email
from app.common.ratelimit import counter
from app.core.config import get_settings
from app.core.errors import AppError, NotAuthenticated, ValidationFailed
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.db.base import utcnow
from app.db.tenant import TenantDescriptor
from app.modules.identity.models import PasswordResetToken, RefreshToken, User, UserSession
from app.modules.identity.passwords import validate_password

MODULE = "auth"

# A real Argon2 hash used to equalise timing when the username does not exist.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


class InvalidCredentials(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    message = "Invalid username or password"


class AccountLocked(AppError):
    status_code = 403
    code = "ACCOUNT_LOCKED"
    message = "Account temporarily locked after repeated failed logins"


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many attempts. Please try again later."


class SessionExpired(NotAuthenticated):
    code = "SESSION_EXPIRED"
    message = "Your session has expired. Please sign in again."


@dataclass
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    session: UserSession
    user: User


# ----------------------------------------------------------------------------- helpers
def _find_user(session: Session, login: str) -> User | None:
    login = login.strip().lower()
    return session.scalars(
        select(User).where(or_(User.username == login, User.email == login), User.is_deleted.is_(False))
    ).first()


def _issue_access(tenant: TenantDescriptor, user: User, sess: UserSession) -> tuple[str, int]:
    ttl = get_settings().access_token_ttl_minutes
    token = create_access_token(
        subject=user.public_id, token_type="tenant", tenant_id=tenant.public_id, session_id=sess.public_id
    )
    return token, ttl * 60


def _new_refresh(session: Session, sess: UserSession) -> str:
    raw = generate_token(32)
    session.add(RefreshToken(session_id=sess.id, token_hash=hash_token(raw), expires_at=sess.expires_at))
    return raw


def revoke_session(sess: UserSession, reason: str) -> None:
    if sess.revoked_at is None:
        sess.revoked_at = utcnow()
        sess.revoke_reason = reason


def revoke_all_sessions(session: Session, user_id: int, reason: str, *, except_id: int | None = None) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoke_reason=reason)
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    return session.execute(stmt).rowcount or 0


def check_session_alive(sess: UserSession, now: datetime | None = None) -> None:
    """Raise if revoked, past absolute expiry, or idle longer than the configured timeout."""
    now = now or utcnow()
    if sess.revoked_at is not None:
        raise SessionExpired(
            "This session has been signed out" if sess.revoke_reason != "IDLE_TIMEOUT" else None,
            code="SESSION_REVOKED" if sess.revoke_reason != "IDLE_TIMEOUT" else "SESSION_EXPIRED",
        )
    if now >= sess.expires_at:
        revoke_session(sess, "EXPIRED")
        raise SessionExpired()
    if now - sess.last_activity_at > timedelta(minutes=get_settings().idle_timeout_minutes):
        revoke_session(sess, "IDLE_TIMEOUT")
        raise SessionExpired()


def touch_session(sess: UserSession, now: datetime | None = None) -> None:
    now = now or utcnow()
    if (now - sess.last_activity_at).total_seconds() >= get_settings().session_touch_interval_seconds:
        sess.last_activity_at = now


# ----------------------------------------------------------------------------- login
def login(
    session: Session, tenant: TenantDescriptor, login_name: str, password: str, request: Request | None = None
) -> IssuedTokens:
    settings = get_settings()
    window = settings.lockout_minutes * 60
    ip = client_ip(request) or "unknown"
    rl_key = f"login-ip:{tenant.code}:{ip}"
    if counter().get(rl_key) >= settings.max_failed_logins_per_ip:
        raise RateLimited()

    now = utcnow()
    user = _find_user(session, login_name)
    if user is None:
        verify_password(_DUMMY_HASH, password)
        counter().hit(rl_key, window)
        record_audit(
            session,
            action="LOGIN_FAILED",
            module=MODULE,
            request=request,
            remarks=f"unknown user '{login_name[:100]}'",
        )
        session.commit()
        raise InvalidCredentials()

    if user.locked_until and user.locked_until > now:
        record_audit(
            session,
            action="LOGIN_BLOCKED",
            module=MODULE,
            user_id=user.id,
            request=request,
            entity_type="user",
            entity_id=user.public_id,
            remarks="account locked",
        )
        session.commit()
        raise AccountLocked()

    if not verify_password(user.password_hash, password) or not user.is_active:
        counter().hit(rl_key, window)
        user.failed_login_count += 1
        remarks = "inactive account" if user.is_active is False else "bad password"
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_count = 0
            remarks += "; account locked"
        record_audit(
            session,
            action="LOGIN_FAILED",
            module=MODULE,
            user_id=user.id,
            request=request,
            entity_type="user",
            entity_id=user.public_id,
            remarks=remarks,
        )
        session.commit()
        raise InvalidCredentials()

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    sess = UserSession(
        user_id=user.id,
        issued_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=settings.refresh_token_ttl_hours),
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255] if request else None,
    )
    session.add(sess)
    session.flush()
    refresh = _new_refresh(session, sess)
    access, expires_in = _issue_access(tenant, user, sess)
    record_audit(
        session,
        action="LOGIN",
        module=MODULE,
        user_id=user.id,
        request=request,
        entity_type="session",
        entity_id=sess.public_id,
    )
    return IssuedTokens(access, expires_in, refresh, sess, user)


# ----------------------------------------------------------------------------- refresh
def refresh(
    session: Session, tenant: TenantDescriptor, raw_token: str | None, request: Request | None = None
) -> IssuedTokens:
    if not raw_token:
        raise NotAuthenticated("Refresh token missing", code="INVALID_REFRESH_TOKEN")
    token = session.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    ).first()
    if token is None:
        raise NotAuthenticated("Invalid refresh token", code="INVALID_REFRESH_TOKEN")
    sess = token.session
    now = utcnow()
    if token.used_at is not None:
        # Token replay ⇒ assume theft: kill the session for everyone holding it.
        revoke_session(sess, "TOKEN_REUSE")
        record_audit(
            session,
            action="REFRESH_TOKEN_REUSE",
            module=MODULE,
            user_id=sess.user_id,
            request=request,
            entity_type="session",
            entity_id=sess.public_id,
        )
        session.commit()
        raise NotAuthenticated("Refresh token already used", code="REFRESH_TOKEN_REUSED")
    try:
        check_session_alive(sess, now)
    except SessionExpired:
        session.commit()  # persist the revocation
        raise
    if token.expires_at <= now:
        raise SessionExpired()
    user = sess.user
    if not user.is_active or user.is_deleted:
        revoke_session(sess, "USER_DISABLED")
        session.commit()
        raise NotAuthenticated()

    token.used_at = now
    sess.last_activity_at = now
    new_refresh = _new_refresh(session, sess)
    access, expires_in = _issue_access(tenant, user, sess)
    return IssuedTokens(access, expires_in, new_refresh, sess, user)


def session_from_refresh(session: Session, raw_token: str | None) -> UserSession | None:
    if not raw_token:
        return None
    token = session.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    ).first()
    return token.session if token else None


def logout(
    session: Session, sess: UserSession, request: Request | None = None, reason: str = "LOGOUT"
) -> None:
    revoke_session(sess, reason)
    record_audit(
        session,
        action="LOGOUT",
        module=MODULE,
        user_id=sess.user_id,
        request=request,
        entity_type="session",
        entity_id=sess.public_id,
        remarks=reason,
    )


# ----------------------------------------------------------------------------- passwords
def change_password(
    session: Session, user: User, current_sess: UserSession, current: str, new: str, request: Request | None
) -> None:
    if not verify_password(user.password_hash, current):
        raise ValidationFailed(
            "Current password is incorrect",
            code="INVALID_CURRENT_PASSWORD",
            details=[{"field": "current_password", "message": "Incorrect password"}],
        )
    if verify_password(user.password_hash, new):
        raise ValidationFailed(
            details=[{"field": "new_password", "message": "Must differ from current password"}]
        )
    validate_password(new, username=user.username, email=user.email, field="new_password")
    user.password_hash = hash_password(new)
    user.password_changed_at = utcnow()
    user.must_change_password = False
    revoked = revoke_all_sessions(session, user.id, "PASSWORD_CHANGED", except_id=current_sess.id)
    record_audit(
        session,
        action="PASSWORD_CHANGED",
        module=MODULE,
        user_id=user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
        remarks=f"{revoked} other session(s) revoked",
    )


def send_reset_link(
    session: Session, tenant: TenantDescriptor, user: User, request: Request | None, *, invite: bool = False
) -> str:
    settings = get_settings()
    raw = generate_token(32)
    ttl = settings.password_reset_ttl_minutes if not invite else 72 * 60
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(minutes=ttl),
            requested_ip=client_ip(request),
        )
    )
    action = "ACCOUNT_INVITE_SENT" if invite else "PASSWORD_RESET_REQUESTED"
    record_audit(
        session,
        action=action,
        module=MODULE,
        user_id=user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
    )
    link = (
        settings.app_url_template.format(subdomain=tenant.subdomain).rstrip("/")
        + f"/reset-password?token={raw}"
    )
    if invite:
        subject = f"{tenant.name}: your ParishSphere account"
        intro = (
            f"An account has been created for you at {tenant.name} (username: {user.username}).\n"
            f"Open this link within 72 hours to set your password:"
        )
    else:
        subject = f"{tenant.name}: reset your ParishSphere password"
        intro = (
            f"A password reset was requested for your account at {tenant.name}.\n"
            f"Open this link within {ttl} minutes to choose a new password:"
        )
    assert user.email
    send_email(
        user.email,
        subject,
        f"Dear {user.full_name},\n\n{intro}\n\n{link}\n\n"
        "If you did not expect this email, you can ignore it.\n\n— ParishSphere",
    )
    return raw


def request_password_reset(
    session: Session, tenant: TenantDescriptor, login_name: str, request: Request | None
) -> str | None:
    """Create a reset token and email it. Returns the raw token (for tests); callers never expose it."""
    ip = client_ip(request) or "unknown"
    if counter().hit(f"reset-ip:{tenant.code}:{ip}", 3600) > 10:
        raise RateLimited()
    user = _find_user(session, login_name)
    if user is None or not user.is_active or not user.email:
        return None
    return send_reset_link(session, tenant, user, request)


def reset_password(session: Session, raw_token: str, new_password: str, request: Request | None) -> User:
    token = session.scalars(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token))
    ).first()
    now = utcnow()
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise ValidationFailed("This reset link is invalid or has expired", code="INVALID_RESET_TOKEN")
    user = session.get(User, token.user_id)
    if user is None or user.is_deleted or not user.is_active:
        raise ValidationFailed("This reset link is invalid or has expired", code="INVALID_RESET_TOKEN")
    validate_password(new_password, username=user.username, email=user.email, field="new_password")
    token.used_at = now
    session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    revoke_all_sessions(session, user.id, "PASSWORD_RESET")
    record_audit(
        session,
        action="PASSWORD_RESET",
        module=MODULE,
        user_id=user.id,
        request=request,
        entity_type="user",
        entity_id=user.public_id,
    )
    return user


# ----------------------------------------------------------------------------- user admin helpers
def create_user(
    session: Session,
    *,
    username: str,
    full_name: str,
    password: str,
    email: str | None = None,
    phone: str | None = None,
    must_change_password: bool = True,
    actor_id: int | None = None,
    enforce_policy: bool = True,
) -> User:
    from app.core.errors import Conflict

    username = username.strip().lower()
    email = email.strip().lower() if email else None
    if session.scalars(select(User.id).where(User.username == username)).first() is not None:
        raise Conflict("Username already exists", code="USERNAME_EXISTS")
    if email and session.scalars(select(User.id).where(User.email == email)).first() is not None:
        raise Conflict("Email already in use", code="EMAIL_EXISTS")
    if enforce_policy:
        validate_password(password, username=username, email=email)
    user = User(
        username=username,
        email=email,
        full_name=full_name,
        phone=phone,
        password_hash=hash_password(password),
        must_change_password=must_change_password,
        password_changed_at=utcnow(),
        created_by=actor_id,
    )
    session.add(user)
    session.flush()
    return user


def create_initial_admin(
    session: Session,
    tenant: TenantDescriptor,
    *,
    username: str,
    full_name: str,
    email: str | None,
    password: str | None = None,
) -> tuple[User, str | None]:
    """Create the parish's first administrator.

    With ``password`` the account uses it (CLI). Without, a random password is set and – when an
    email is available – a 72-hour "set your password" link is emailed. Returns the user and the
    generated temporary password when one must be shown to the operator (no email available).
    """
    temp: str | None = None
    if password is None:
        password = generate_token(18) + "-Aa1"
        temp = password if not email else None
    user = create_user(
        session,
        username=username,
        full_name=full_name,
        email=email,
        password=password,
        must_change_password=True,
        enforce_policy=temp is None and email is None,
    )
    record_audit(
        session,
        action="CREATE",
        module="users",
        user_id=None,
        entity_type="user",
        entity_id=user.public_id,
        new={"username": user.username, "bootstrap_admin": True},
    )
    from app.modules.rbac.catalog import ADMIN_ROLE
    from app.modules.rbac.service import assign_role, role_by_code

    admin_role = role_by_code(session, ADMIN_ROLE)
    if admin_role is not None:
        assign_role(session, user, admin_role, remarks="initial parish administrator")
    if email:
        send_reset_link(session, tenant, user, None, invite=True)
    return user, temp

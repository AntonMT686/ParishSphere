"""Parish authentication API (``/api/v1/auth``)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record_audit
from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.modules.identity import service
from app.modules.identity.deps import Auth
from app.modules.identity.models import User, UserSession
from app.modules.identity.schemas import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    MeOut,
    MessageOut,
    ResetPasswordIn,
    SessionOut,
    TokenOut,
)
from app.modules.rbac.service import EffectivePermissions, effective_permissions
from app.tenancy.deps import CurrentTenant, TenantSession

AUTH_PATH = "/api/v1/auth"
router = APIRouter(prefix="/auth", tags=["auth"])


class CsrfFailed(AppError):
    status_code = 403
    code = "CSRF_FAILED"
    message = "Missing or invalid CSRF token"


# ----------------------------------------------------------------------------- cookies
def _set_auth_cookies(response: Response, refresh_token: str) -> None:
    s = get_settings()
    max_age = s.refresh_token_ttl_hours * 3600
    response.set_cookie(
        s.refresh_cookie_name,
        refresh_token,
        max_age=max_age,
        path=AUTH_PATH,
        httponly=True,
        secure=s.secure_cookies,
        samesite="strict",
    )
    # Double-submit CSRF token: readable by the SPA, echoed in X-CSRF-Token on refresh/logout.
    response.set_cookie(
        s.csrf_cookie_name,
        secrets.token_urlsafe(24),
        max_age=max_age,
        path="/",
        httponly=False,
        secure=s.secure_cookies,
        samesite="strict",
    )


def _clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.refresh_cookie_name, path=AUTH_PATH, secure=s.secure_cookies, samesite="strict")
    response.delete_cookie(s.csrf_cookie_name, path="/", secure=s.secure_cookies, samesite="strict")


def _verify_csrf(request: Request) -> None:
    cookie = request.cookies.get(get_settings().csrf_cookie_name)
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise CsrfFailed()


def _me(db: Session, user: User, eff: EffectivePermissions | None = None) -> MeOut:
    eff = eff or effective_permissions(db, user)
    out = MeOut.model_validate(user)
    out.roles = sorted(eff.role_codes)
    out.permissions = sorted(eff.all_codes)
    return out


def _token_out(db: Session, issued: service.IssuedTokens) -> TokenOut:
    return TokenOut(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        idle_timeout_seconds=get_settings().idle_timeout_minutes * 60,
        user=_me(db, issued.user),
    )


# ----------------------------------------------------------------------------- endpoints
@router.post("/login", response_model=TokenOut)
def login(
    body: LoginIn, request: Request, response: Response, tenant: CurrentTenant, db: TenantSession
) -> TokenOut:
    issued = service.login(db, tenant, body.username, body.password, request)
    _set_auth_cookies(response, issued.refresh_token)
    return _token_out(db, issued)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, tenant: CurrentTenant, db: TenantSession) -> TokenOut:
    """Rotate the refresh token (cookie) and return a new access token. Also extends idle time."""
    _verify_csrf(request)
    try:
        issued = service.refresh(db, tenant, request.cookies.get(get_settings().refresh_cookie_name), request)
    except AppError:
        _clear_auth_cookies(response)
        raise
    _set_auth_cookies(response, issued.refresh_token)
    return _token_out(db, issued)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, tenant: CurrentTenant, db: TenantSession) -> Response:
    """Revoke the current session. Works with an expired access token (uses the refresh cookie)."""
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    if raw:
        _verify_csrf(request)
        sess = service.session_from_refresh(db, raw)
        if sess is not None:
            service.logout(db, sess, request)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(request: Request, auth: Auth, db: TenantSession) -> Response:
    count = service.revoke_all_sessions(db, auth.user.id, "LOGOUT_ALL")
    record_audit(
        db,
        action="LOGOUT_ALL",
        module=service.MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="user",
        entity_id=auth.user.public_id,
        remarks=f"{count} session(s)",
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response


@router.get("/me", response_model=MeOut)
def me(auth: Auth) -> MeOut:
    return _me(auth.db, auth.user, auth.permissions)


@router.post("/password/change", response_model=MessageOut)
def change_password(body: ChangePasswordIn, request: Request, auth: Auth, db: TenantSession) -> MessageOut:
    service.change_password(db, auth.user, auth.session, body.current_password, body.new_password, request)
    return MessageOut(message="Password changed. Other sessions have been signed out.")


@router.post("/password/forgot", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: ForgotPasswordIn, request: Request, tenant: CurrentTenant, db: TenantSession
) -> MessageOut:
    service.request_password_reset(db, tenant, body.username, request)
    # Identical response whether or not the account exists (no user enumeration).
    return MessageOut(message="If an account with an email address exists, a reset link has been sent.")


@router.post("/password/reset", response_model=MessageOut)
def reset_password(body: ResetPasswordIn, request: Request, db: TenantSession) -> MessageOut:
    service.reset_password(db, body.token, body.new_password, request)
    return MessageOut(message="Password updated. Please sign in with your new password.")


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(auth: Auth, db: TenantSession) -> list[SessionOut]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == auth.user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_activity_at.desc())
    ).all()
    return [
        SessionOut(
            id=s.public_id,
            issued_at=s.issued_at,
            last_activity_at=s.last_activity_at,
            expires_at=s.expires_at,
            ip=s.ip,
            user_agent=s.user_agent,
            current=s.id == auth.session.id,
        )
        for s in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, request: Request, auth: Auth, db: TenantSession) -> Response:
    sess = db.scalars(
        select(UserSession).where(UserSession.public_id == session_id, UserSession.user_id == auth.user.id)
    ).first()
    if sess is None:
        raise NotFound()
    service.logout(db, sess, request, reason="REVOKED_BY_USER")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

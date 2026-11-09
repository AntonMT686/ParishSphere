"""Notification service.

``emit()`` writes in-app notifications and queues outbound messages *in the caller's transaction*. After
that transaction commits, queued messages are delivered by Celery (when a broker is configured) or
in-process. A rolled-back transaction therefore never sends anything.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import structlog
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.common.email import send_email
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.db.base import utcnow
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.identity.models import User
from app.modules.notifications.catalog import EMAIL, EVENTS, IN_APP, EventDef
from app.modules.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
    OutboundMessage,
)

log = structlog.get_logger(__name__)

_env = SandboxedEnvironment(autoescape=False, trim_blocks=True)
_PENDING_KEY = "ps_outbound"


# ----------------------------------------------------------------------------- templates
def event_def(code: str) -> EventDef:
    try:
        return EVENTS[code]
    except KeyError as exc:
        raise ValueError(f"Unknown notification event {code!r}") from exc


def render(text: str, context: dict[str, Any]) -> str:
    return _env.from_string(text).render(**context).strip()


def validate_template(event_code: str, subject: str, body: str) -> None:
    sample = {v: f"<{v}>" for v in event_def(event_code).variables}
    try:
        render(subject, sample)
        render(body, sample)
    except TemplateError as exc:
        raise ValidationFailed(
            "Template is invalid", code="INVALID_TEMPLATE", details=[{"field": "body", "message": str(exc)}]
        ) from exc


def template_for(session: Session, event_code: str, channel: str, language: str) -> tuple[str, str]:
    override = session.scalars(
        select(NotificationTemplate).where(
            NotificationTemplate.event_code == event_code,
            NotificationTemplate.channel == channel,
            NotificationTemplate.language == language,
        )
    ).first()
    if override is not None:
        return override.subject, override.body
    templates = event_def(event_code).templates
    return templates.get(language) or templates["en"]


# ----------------------------------------------------------------------------- preferences
def channel_enabled(
    session: Session,
    user_id: int,
    event_code: str,
    channel: str,
    cache: dict[tuple[int, str, str], bool] | None = None,
) -> bool:
    key = (user_id, event_code, channel)
    if cache is not None and key in cache:
        return cache[key]
    pref = session.scalars(
        select(NotificationPreference.enabled).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.event_code == event_code,
            NotificationPreference.channel == channel,
        )
    ).first()
    enabled = pref if pref is not None else channel in event_def(event_code).default_channels
    if cache is not None:
        cache[key] = enabled
    return enabled


# ----------------------------------------------------------------------------- emit
def emit(
    session: Session,
    tenant: TenantDescriptor,
    event_code: str,
    recipients: Iterable[User | int],
    context: dict[str, Any],
    *,
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    exclude_user_id: int | None = None,
) -> list[Notification]:
    """Notify ``recipients`` (users or user ids). Returns the in-app notifications created."""
    ev = event_def(event_code)
    ids = {r.id if isinstance(r, User) else r for r in recipients} - {exclude_user_id}
    if not ids:
        return []
    users = session.scalars(
        select(User).where(User.id.in_(ids), User.is_active.is_(True), User.is_deleted.is_(False))
    ).all()
    settings = get_settings()
    cache: dict[tuple[int, str, str], bool] = {}
    created: list[Notification] = []
    for user in users:
        lang = user.preferred_language if user.preferred_language in ev.templates else "en"
        ctx = {"recipient": user.full_name, **context}
        if channel_enabled(session, user.id, event_code, IN_APP, cache):
            subject, body = template_for(session, event_code, IN_APP, lang)
            n = Notification(
                user_id=user.id,
                event_code=event_code,
                title=render(subject, ctx)[:255],
                body=render(body, ctx),
                link=link,
                entity_type=entity_type,
                entity_id=entity_id,
                is_important=ev.important,
            )
            session.add(n)
            created.append(n)
        if user.email and channel_enabled(session, user.id, event_code, EMAIL, cache):
            subject, body = template_for(session, event_code, EMAIL, lang)
            url = (
                settings.app_url_template.format(subdomain=tenant.subdomain).rstrip("/") + link
                if link
                else None
            )
            text = render(body, ctx)
            footer = f"\n\n{url}" if url else ""
            msg = OutboundMessage(
                channel=EMAIL,
                recipient=user.email,
                user_id=user.id,
                event_code=event_code,
                subject=f"{tenant.name}: {render(subject, ctx)}"[:255],
                body=f"Dear {user.full_name},\n\n{text}{footer}\n\n— {tenant.name} (ParishSphere)\n"
                f"Manage notification preferences in your profile.",
            )
            session.add(msg)
            session.flush()
            session.info.setdefault(_PENDING_KEY, []).append((tenant.code, msg.id))
    session.flush()
    return created


# ----------------------------------------------------------------------------- delivery
def deliver(tenant_code: str, message_id: int, *, raise_errors: bool = False) -> str:
    """Send one outbound message; idempotent (already-sent messages are skipped). Returns new status."""
    from app.tenancy.resolver import resolve_tenant

    tenant = resolve_tenant(code=tenant_code)
    if tenant is None:
        return "SKIPPED"
    with tenant_session_scope(tenant) as session:
        msg = session.get(OutboundMessage, message_id, with_for_update=True)
        if msg is None or msg.status == "SENT":
            return "SKIPPED"
        msg.attempts += 1
        try:
            if msg.channel != EMAIL:
                raise RuntimeError(f"No provider configured for channel {msg.channel}")
            send_email(msg.recipient, msg.subject or "", msg.body, raise_errors=True)
        except Exception as exc:
            msg.status = "FAILED"
            msg.last_error = str(exc)[:2000]
            log.warning("outbound_delivery_failed", tenant=tenant_code, message=message_id, error=str(exc))
            session.commit()
            if raise_errors:
                raise
            return "FAILED"
        msg.status = "SENT"
        msg.sent_at = utcnow()
        msg.last_error = None
        return "SENT"


def _dispatch(items: list[tuple[str, int]]) -> None:
    if get_settings().use_celery:
        from app.modules.notifications.tasks import send_outbound

        for tenant_code, message_id in items:
            send_outbound.delay(tenant_code, message_id)
        return
    for tenant_code, message_id in items:
        try:
            deliver(tenant_code, message_id)
        except Exception:  # pragma: no cover - deliver() records failures itself
            log.exception("outbound_inline_delivery_error")


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING_KEY, None)
    if pending:
        _dispatch(pending)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)

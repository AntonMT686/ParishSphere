"""Notifications API (``/api/v1/notifications``): inbox, preferences, templates, broadcast."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select, update

from app.common.audit import record_audit
from app.common.pagination import Page, PageQuery, paginate
from app.core.errors import NotFound, ValidationFailed
from app.db.base import utcnow
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.notifications import service
from app.modules.notifications.catalog import CHANNELS, EVENTS, LANGUAGES
from app.modules.notifications.models import Notification, NotificationPreference, NotificationTemplate
from app.modules.notifications.schemas import (
    BroadcastIn,
    NotificationOut,
    PreferenceIn,
    PreferenceOut,
    TemplateIn,
    TemplateOut,
    UnreadCountOut,
)
from app.modules.rbac.deps import require_perm
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.rbac.service import PermissionScope, assignment_active_clause
from app.tenancy.deps import TenantSession

router = APIRouter(prefix="/notifications", tags=["notifications"])

CanViewSettings = Annotated[PermissionScope, Depends(require_perm("settings.view", parish_wide=True))]
CanUpdateSettings = Annotated[PermissionScope, Depends(require_perm("settings.update", parish_wide=True))]


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.public_id,
        event_code=n.event_code,
        title=n.title,
        body=n.body,
        link=n.link,
        entity_type=n.entity_type,
        entity_id=n.entity_id,
        is_important=n.is_important,
        is_read=n.is_read,
        created_at=n.created_at,
    )


# ----------------------------------------------------------------------------- inbox
@router.get("", response_model=Page[NotificationOut])
def my_notifications(
    auth: Auth, db: TenantSession, params: PageQuery, unread_only: bool = False
) -> Page[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == auth.user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
    return paginate(db, stmt, params, _out)


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(auth: Auth, db: TenantSession) -> UnreadCountOut:
    count = db.scalar(
        select(func.count()).where(Notification.user_id == auth.user.id, Notification.is_read.is_(False))
    )
    return UnreadCountOut(unread=count or 0)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: str, auth: Auth, db: TenantSession) -> NotificationOut:
    n = db.scalars(
        select(Notification).where(
            Notification.public_id == notification_id, Notification.user_id == auth.user.id
        )
    ).first()
    if n is None:
        raise NotFound()
    if not n.is_read:
        n.is_read, n.read_at = True, utcnow()
    return _out(n)


@router.post("/read-all", response_model=UnreadCountOut)
def mark_all_read(auth: Auth, db: TenantSession) -> UnreadCountOut:
    db.execute(
        update(Notification)
        .where(Notification.user_id == auth.user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=utcnow())
    )
    return UnreadCountOut(unread=0)


# ----------------------------------------------------------------------------- preferences
@router.get("/preferences", response_model=list[PreferenceOut])
def my_preferences(auth: Auth, db: TenantSession) -> list[PreferenceOut]:
    saved = {
        (p.event_code, p.channel): p.enabled
        for p in db.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == auth.user.id)
        )
    }
    out = []
    for ev in EVENTS.values():
        for ch in CHANNELS:
            default = ch in ev.default_channels
            out.append(
                PreferenceOut(
                    event_code=ev.code,
                    description=ev.description,
                    channel=ch,
                    enabled=saved.get((ev.code, ch), default),
                    default=default,
                )
            )
    return out


@router.put("/preferences", response_model=list[PreferenceOut])
def update_preferences(body: list[PreferenceIn], auth: Auth, db: TenantSession) -> list[PreferenceOut]:
    for item in body:
        if item.event_code not in EVENTS:
            raise ValidationFailed(
                details=[{"field": "event_code", "message": f"Unknown event {item.event_code}"}]
            )
        pref = db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id == auth.user.id,
                NotificationPreference.event_code == item.event_code,
                NotificationPreference.channel == item.channel,
            )
        ).first()
        if pref is None:
            db.add(
                NotificationPreference(
                    user_id=auth.user.id,
                    event_code=item.event_code,
                    channel=item.channel,
                    enabled=item.enabled,
                )
            )
        else:
            pref.enabled = item.enabled
    db.flush()
    return my_preferences(auth, db)


# ----------------------------------------------------------------------------- templates
@router.get("/templates", response_model=list[TemplateOut])
def list_templates(_: CanViewSettings, db: TenantSession) -> list[TemplateOut]:
    overrides = {(t.event_code, t.channel, t.language): t for t in db.scalars(select(NotificationTemplate))}
    out = []
    for ev in EVENTS.values():
        for ch in CHANNELS:
            for lang in LANGUAGES:
                o = overrides.get((ev.code, ch, lang))
                subject, body = (o.subject, o.body) if o else ev.templates.get(lang, ev.templates["en"])
                out.append(
                    TemplateOut(
                        event_code=ev.code,
                        description=ev.description,
                        variables=list(ev.variables),
                        channel=ch,
                        language=lang,
                        subject=subject,
                        body=body,
                        is_override=o is not None,
                    )
                )
    return out


def _check_key(event_code: str, channel: str, language: str) -> None:
    if event_code not in EVENTS or channel not in CHANNELS or language not in LANGUAGES:
        raise NotFound("Unknown template")


@router.put("/templates/{event_code}/{channel}/{language}", response_model=TemplateOut)
def override_template(
    event_code: str,
    channel: str,
    language: str,
    body: TemplateIn,
    request: Request,
    auth: Auth,
    _: CanUpdateSettings,
    db: TenantSession,
) -> TemplateOut:
    _check_key(event_code, channel, language)
    service.validate_template(event_code, body.subject, body.body)
    t = db.scalars(
        select(NotificationTemplate).where(
            NotificationTemplate.event_code == event_code,
            NotificationTemplate.channel == channel,
            NotificationTemplate.language == language,
        )
    ).first()
    if t is None:
        t = NotificationTemplate(
            event_code=event_code, channel=channel, language=language, subject=body.subject, body=body.body
        )
        db.add(t)
    else:
        t.subject, t.body = body.subject, body.body
    t.updated_by = auth.user.id
    record_audit(
        db,
        action="UPDATE",
        module="notifications",
        user_id=auth.user.id,
        request=request,
        entity_type="notification_template",
        entity_id=f"{event_code}/{channel}/{language}",
        new=body.model_dump(),
    )
    ev = EVENTS[event_code]
    return TemplateOut(
        event_code=event_code,
        description=ev.description,
        variables=list(ev.variables),
        channel=channel,
        language=language,
        subject=t.subject,
        body=t.body,
        is_override=True,
    )


@router.delete("/templates/{event_code}/{channel}/{language}", status_code=status.HTTP_204_NO_CONTENT)
def reset_template(
    event_code: str,
    channel: str,
    language: str,
    request: Request,
    auth: Auth,
    _: CanUpdateSettings,
    db: TenantSession,
) -> Response:
    """Revert to the built-in default template."""
    _check_key(event_code, channel, language)
    t = db.scalars(
        select(NotificationTemplate).where(
            NotificationTemplate.event_code == event_code,
            NotificationTemplate.channel == channel,
            NotificationTemplate.language == language,
        )
    ).first()
    if t is not None:
        db.delete(t)
        record_audit(
            db,
            action="DELETE",
            module="notifications",
            user_id=auth.user.id,
            request=request,
            entity_type="notification_template",
            entity_id=f"{event_code}/{channel}/{language}",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- broadcast
@router.post("/broadcast", status_code=status.HTTP_202_ACCEPTED)
def broadcast(
    body: BroadcastIn, request: Request, auth: Auth, _: CanUpdateSettings, db: TenantSession
) -> dict[str, int]:
    """Send a general message to all active users, or to holders of the given roles."""
    stmt = select(User.id).where(User.is_active.is_(True), User.is_deleted.is_(False))
    if body.role_codes:
        stmt = stmt.where(
            User.id.in_(
                select(UserRoleAssignment.user_id)
                .join(Role, Role.id == UserRoleAssignment.role_id)
                .where(Role.code.in_([c.upper() for c in body.role_codes]), assignment_active_clause())
            )
        )
    ids = list(db.scalars(stmt))
    created = service.emit(
        db,
        auth.tenant,
        "general.message",
        ids,
        {"title": body.title, "message": body.message},
        link=body.link,
    )
    record_audit(
        db,
        action="BROADCAST",
        module="notifications",
        user_id=auth.user.id,
        request=request,
        new=body.model_dump(),
        remarks=f"{len(ids)} recipient(s)",
    )
    return {"recipients": len(ids), "in_app": len(created)}

"""Notice lifecycle, audiences and publication.

Visibility follows the publication window directly: an approved notice is live from ``publish_at`` until
``expires_at``. The periodic job only flips the status to PUBLISHED and notifies the audience, so a late
job never delays a notice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from app.common.sequences import next_code
from app.core.errors import Conflict, NotFound
from app.db.base import utcnow
from app.db.tenant import TenantDescriptor
from app.modules.activities.service import parish_now
from app.modules.identity.models import User
from app.modules.notices.models import Notice
from app.modules.notifications.service import emit
from app.modules.org_units.models import OrgUnitOfficeBearer
from app.modules.org_units.service import current_bearers_stmt
from app.modules.rbac.models import UserRoleAssignment
from app.modules.rbac.service import assignment_active_clause, users_with_permission
from app.modules.workflow import service as wf
from app.modules.workflow.models import WorkflowInstance
from app.modules.workflow.registry import WorkflowHandler, register_handler

EDITABLE = ("DRAFT", "REWORK")
LIVE_STATUSES = ("APPROVED", "PUBLISHED")


def get_notice(db: Session, public_id: str) -> Notice:
    n = db.scalar(select(Notice).where(Notice.public_id == public_id, Notice.is_deleted.is_(False)))
    if n is None:
        raise NotFound("Notice not found")
    return n


def new_notice(db: Session, data: dict[str, Any], actor_id: int) -> Notice:
    n = Notice(
        code=next_code(db, "NOTICE", data["publish_at"].date()), status="DRAFT", created_by=actor_id, **data
    )
    db.add(n)
    db.flush()
    return n


def state(n: Notice, now: datetime) -> str:
    """What readers experience: DRAFT, IN_REVIEW, REWORK, SCHEDULED, LIVE, EXPIRED, ARCHIVED, REJECTED."""
    if n.status in LIVE_STATUSES:
        if n.expires_at is not None and n.expires_at <= now:
            return "EXPIRED"
        return "LIVE" if n.publish_at <= now else "SCHEDULED"
    return n.status


def live_clause(now: datetime) -> ColumnElement[bool]:
    return and_(
        Notice.status.in_(LIVE_STATUSES),
        Notice.is_deleted.is_(False),
        Notice.publish_at <= now,
        or_(Notice.expires_at.is_(None), Notice.expires_at > now),
    )


# ============================================================================ audiences
def user_unit_ids(db: Session, user_id: int) -> set[int]:
    """Organisations a user belongs to through a scoped role or a current office."""
    units = set(
        db.scalars(
            select(UserRoleAssignment.org_unit_id).where(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.org_unit_id.is_not(None),
                assignment_active_clause(),
            )
        )
    )
    today = datetime.now().date()
    units |= set(
        db.scalars(
            select(OrgUnitOfficeBearer.org_unit_id).where(
                OrgUnitOfficeBearer.user_id == user_id,
                OrgUnitOfficeBearer.ended_at.is_(None),
                OrgUnitOfficeBearer.valid_from <= today,
                or_(OrgUnitOfficeBearer.valid_to.is_(None), OrgUnitOfficeBearer.valid_to >= today),
            )
        )
    )
    return {u for u in units if u is not None}


def audience_ok(n: Notice, unit_ids: set[int]) -> bool:
    if n.audience.get("all", True):
        return True
    return bool(set(n.audience.get("org_units") or []) & unit_ids)


def audience_users(db: Session, n: Notice) -> set[int]:
    if n.audience.get("all", True):
        return {u.id for u in users_with_permission(db, "notice.view")}
    out: set[int] = set()
    for unit_id in n.audience.get("org_units") or []:
        out |= {
            uid
            for uid in db.scalars(
                select(UserRoleAssignment.user_id).where(
                    UserRoleAssignment.org_unit_id == unit_id, assignment_active_clause()
                )
            )
        }
        out |= {b.user_id for b in db.scalars(current_bearers_stmt(unit_id)) if b.user_id}
    active = set(db.scalars(select(User.id).where(User.id.in_(out), User.is_active.is_(True))))
    return active


# ============================================================================ workflow
def submit(
    db: Session, tenant: TenantDescriptor, n: Notice, actor_id: int, comment: str | None = None
) -> WorkflowInstance:
    if n.status == "REWORK":
        inst = wf.active_instance(db, "NOTICE", n.public_id)
        if inst is None:
            raise Conflict("No approval is waiting for this notice", code="INVALID_STATE")
        return wf.resubmit(db, tenant, inst, actor_id, comment, title=n.title)
    if n.status != "DRAFT":
        raise Conflict("Only drafts can be submitted", code="INVALID_STATE")
    if n.expires_at is not None and n.expires_at <= parish_now(db):
        raise Conflict("The expiry date has already passed", code="NOTICE_EXPIRED")
    return wf.submit(
        db,
        tenant,
        entity_type="NOTICE",
        entity_id=n.public_id,
        title=n.title,
        actor_id=actor_id,
        org_unit_id=n.org_unit_id,
        context={"category": n.category},
        link=f"/notices/{n.public_id}",
        comment=comment,
    )


def _set(status: str):  # type: ignore[no-untyped-def]
    def cb(db: Session, inst: WorkflowInstance) -> None:
        n = get_notice(db, inst.entity_id)
        n.status = status
        if status == "IN_REVIEW":
            n.submitted_at = utcnow()
        elif status == "APPROVED":
            n.approved_at = utcnow()
            tenant = db.info.get("tenant")
            if tenant is not None and n.publish_at <= parish_now(db):
                publish(db, tenant, n)

    return cb


register_handler(
    "NOTICE",
    WorkflowHandler(
        on_submitted=_set("IN_REVIEW"),
        on_approved=_set("APPROVED"),
        on_rejected=_set("REJECTED"),
        on_rework=_set("REWORK"),
        on_withdrawn=_set("DRAFT"),
    ),
)


# ============================================================================ publication
def publish(db: Session, tenant: TenantDescriptor, n: Notice, now: datetime | None = None) -> None:
    """Mark as published and notify the audience (once)."""
    now = now or parish_now(db)
    if n.status not in LIVE_STATUSES:
        raise Conflict("Only approved notices can be published", code="INVALID_STATE")
    if n.publish_at > now:
        n.publish_at = now  # "publish now" on a scheduled notice
    n.status = "PUBLISHED"
    if n.published_at is None:
        n.published_at = utcnow()
        event = "notice.important" if n.is_important or n.category == "EMERGENCY" else "notice.published"
        emit(
            db,
            tenant,
            event,
            audience_users(db, n),
            {"title": n.title, "category": n.category.title()},
            link=f"/notices/{n.public_id}",
            entity_type="NOTICE",
            entity_id=n.public_id,
        )


def archive(n: Notice, actor_id: int) -> None:
    if n.status not in LIVE_STATUSES:
        raise Conflict("Only approved or published notices can be archived", code="INVALID_STATE")
    n.status, n.archived_at, n.archived_by = "ARCHIVED", utcnow(), actor_id


def publish_due(db: Session, tenant: TenantDescriptor, now: datetime | None = None) -> int:
    """Publish approved notices whose time has come (run every few minutes)."""
    now = now or parish_now(db)
    due = db.scalars(
        select(Notice).where(
            Notice.status == "APPROVED", Notice.is_deleted.is_(False), Notice.publish_at <= now
        )
    ).all()
    for n in due:
        if n.expires_at is None or n.expires_at > now:
            publish(db, tenant, n, now)
    db.flush()
    return len(due)

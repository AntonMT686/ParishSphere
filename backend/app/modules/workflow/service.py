"""Workflow engine: definition selection, assignee resolution, task lifecycle and SLA handling.

Business modules call :func:`submit`, :func:`resubmit` and :func:`withdraw`; reviewers act through
:func:`act`. Every step runs in the caller's transaction (one request = one commit), and the instance
row is locked ``FOR UPDATE`` so two reviewers can never complete the same stage twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.db.base import utcnow
from app.db.tenant import TenantDescriptor
from app.modules.core.models import Setting
from app.modules.identity.models import User
from app.modules.notifications.service import emit
from app.modules.org_units.models import OrgUnit, OrgUnitOfficeBearer, OrgUnitPosition
from app.modules.org_units.service import ancestors, current_bearers_stmt
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.rbac.service import assignment_active_clause
from app.modules.workflow.models import (
    WorkflowAction,
    WorkflowDefinition,
    WorkflowDelegation,
    WorkflowInstance,
    WorkflowTask,
)
from app.modules.workflow.registry import ENTITY_TYPES, handler_for

ACTIVE = ("IN_PROGRESS", "REWORK")
FALLBACK_ROLE = "PARISH_ADMIN"
DECISIONS = ("APPROVE", "REJECT", "RETURN", "DELEGATE")


# ============================================================================ context
@dataclass
class Context:
    """What the definition conditions and assignee rules look at."""

    org_unit_id: int | None = None
    org_unit_type: str | None = None
    amount: float | None = None
    category: str | None = None

    @classmethod
    def build(cls, db: Session, org_unit_id: int | None, extra: dict[str, Any] | None) -> Context:
        extra = extra or {}
        unit_type = None
        if org_unit_id is not None:
            unit = db.get(OrgUnit, org_unit_id)
            if unit is None:
                raise NotFound("Organisation not found")
            unit_type = unit.type.code
        amount = extra.get("amount")
        return cls(
            org_unit_id=org_unit_id,
            org_unit_type=unit_type,
            amount=float(amount) if amount is not None else None,
            category=extra.get("category"),
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "org_unit_id": self.org_unit_id,
            "org_unit_type": self.org_unit_type,
            "amount": self.amount,
            "category": self.category,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Context:
        return cls(**{k: data.get(k) for k in ("org_unit_id", "org_unit_type", "amount", "category")})


def _setting(db: Session, key: str, default: Any) -> Any:
    row = db.get(Setting, key)
    return default if row is None else row.value


# ============================================================================ definitions
def matches(defn: WorkflowDefinition, ctx: Context) -> tuple[bool, int]:
    """Whether every condition holds for ``ctx``; also returns how many conditions were checked."""
    c = defn.conditions or {}
    n = 0
    if c.get("org_unit_types"):
        n += 1
        if ctx.org_unit_type not in c["org_unit_types"]:
            return False, n
    if c.get("parish_level") is not None:
        n += 1
        if bool(c["parish_level"]) != (ctx.org_unit_id is None):
            return False, n
    if c.get("categories"):
        n += 1
        if ctx.category not in c["categories"]:
            return False, n
    for key, ok in (("min_amount", lambda a, v: a >= v), ("max_amount", lambda a, v: a <= v)):
        if c.get(key) is not None:
            n += 1
            if ctx.amount is None or not ok(ctx.amount, float(c[key])):
                return False, n
    return True, n


def select_definition(db: Session, entity_type: str, ctx: Context) -> WorkflowDefinition:
    candidates = db.scalars(
        select(WorkflowDefinition).where(
            WorkflowDefinition.entity_type == entity_type,
            WorkflowDefinition.is_latest.is_(True),
            WorkflowDefinition.is_active.is_(True),
            WorkflowDefinition.is_deleted.is_(False),
        )
    ).all()
    scored = []
    for d in candidates:
        ok, n = matches(d, ctx)
        if ok:
            scored.append((d.priority, n, -d.id, d))
    if not scored:
        label = ENTITY_TYPES[entity_type].label if entity_type in ENTITY_TYPES else entity_type
        raise ValidationFailed(
            f"No approval workflow is configured for this {label.lower()}", code="NO_WORKFLOW_CONFIGURED"
        )
    scored.sort(key=lambda t: t[:3], reverse=True)
    return scored[0][3]


# ============================================================================ assignees
def _role_holders(db: Session, role_code: str, unit_ids: set[int] | None) -> set[int]:
    stmt = (
        select(UserRoleAssignment.user_id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .join(User, User.id == UserRoleAssignment.user_id)
        .where(
            Role.code == role_code,
            Role.is_deleted.is_(False),
            assignment_active_clause(),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if unit_ids is None:
        stmt = stmt.where(UserRoleAssignment.org_unit_id.is_(None))
    else:
        stmt = stmt.where(UserRoleAssignment.org_unit_id.in_(unit_ids))
    return set(db.scalars(stmt))


def _position_holders(db: Session, position_code: str, unit_id: int) -> set[int]:
    stmt = (
        current_bearers_stmt(unit_id)
        .join(OrgUnitPosition, OrgUnitPosition.id == OrgUnitOfficeBearer.position_id)
        .join(User, User.id == OrgUnitOfficeBearer.user_id)
        .where(OrgUnitPosition.code == position_code, User.is_active.is_(True), User.is_deleted.is_(False))
    )
    return {b.user_id for b in db.scalars(stmt) if b.user_id is not None}


def resolve_rule(db: Session, rule: dict[str, Any], ctx: Context) -> set[int]:
    """Users a single assignee rule points to *now*."""
    kind, scope = rule.get("type"), rule.get("scope", "PARISH")
    if kind == "USER":
        uid = db.scalar(
            select(User.id).where(
                User.public_id == rule.get("user_id"), User.is_active.is_(True), User.is_deleted.is_(False)
            )
        )
        return {uid} if uid else set()
    unit_id: int | None = None
    if scope in ("SAME_ORG_UNIT", "PARENT_ORG_UNIT"):
        if ctx.org_unit_id is None:
            return set()
        unit_id = ctx.org_unit_id
        if scope == "PARENT_ORG_UNIT":
            unit = db.get(OrgUnit, unit_id)
            unit_id = unit.parent_id if unit else None
            if unit_id is None:
                return set()
    if kind == "ROLE":
        if unit_id is None:
            return _role_holders(db, rule["role"], None)
        # Roles flow down the organisation tree: a holder for a parent unit also qualifies.
        return _role_holders(db, rule["role"], ancestors(db, {unit_id})[unit_id])
    if kind == "POSITION":
        return _position_holders(db, rule["position"], unit_id) if unit_id is not None else set()
    raise ValidationFailed(f"Unknown assignee rule {kind!r}")


def _delegations(db: Session, entity_type: str, user_ids: set[int], today: date) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = db.scalars(
        select(WorkflowDelegation)
        .where(WorkflowDelegation.delegator_id.in_(user_ids), WorkflowDelegation.ended_at.is_(None))
        .order_by(WorkflowDelegation.id.desc())
    ).all()
    out: dict[int, int] = {}
    for d in rows:
        if d.delegator_id in out or not d.is_active_on(today):
            continue
        if d.entity_types and entity_type not in d.entity_types:
            continue
        delegate = db.get(User, d.delegate_id)
        if delegate and delegate.is_active and not delegate.is_deleted:
            out[d.delegator_id] = d.delegate_id
    return out


@dataclass
class StageAssignees:
    assignees: list[tuple[int, int | None]]  # (user, delegated_from)
    fallback: bool = False


def resolve_stage(
    db: Session, entity_type: str, stage: dict[str, Any], ctx: Context, submitter_id: int | None
) -> StageAssignees:
    users: set[int] = set()
    for rule in stage.get("assignees", []):
        users |= resolve_rule(db, rule, ctx)
    if submitter_id is not None and not _setting(db, "workflow.allow_self_approval", False):
        users.discard(submitter_id)
    fallback = False
    if not users and not stage.get("optional"):
        users = _role_holders(db, FALLBACK_ROLE, None) - {submitter_id}
        fallback = True
    delegated = _delegations(db, entity_type, users, date.today())
    out: dict[int, int | None] = {}
    for u in sorted(users):
        target = delegated.get(u, u)
        if target == submitter_id and target != u:
            target = u  # never route a decision to the submitter through a delegation
        out.setdefault(target, u if target != u else None)
    return StageAssignees(list(out.items()), fallback)


# ============================================================================ helpers
def _log(
    db: Session,
    inst: WorkflowInstance,
    action: str,
    actor_id: int | None,
    *,
    task: WorkflowTask | None = None,
    stage_index: int | None = None,
    comment: str | None = None,
    prev: str | None = None,
    on_behalf_of: int | None = None,
) -> None:
    idx = stage_index if stage_index is not None else (task.stage_index if task else inst.stage_index)
    stages = inst.stages
    db.add(
        WorkflowAction(
            instance_id=inst.id,
            task_id=task.id if task else None,
            cycle=inst.cycle,
            stage_index=idx if idx is not None and idx < len(stages) else None,
            stage_name=stages[idx]["name"] if idx is not None and idx < len(stages) else None,
            action=action,
            actor_id=actor_id,
            on_behalf_of_id=on_behalf_of,
            comment=comment,
            prev_status=prev,
            new_status=inst.status,
        )
    )


def _user_name(db: Session, user_id: int | None) -> str:
    u = db.get(User, user_id) if user_id else None
    return u.full_name if u else "—"


def instance_link(inst: WorkflowInstance) -> str:
    return f"/approvals/{inst.public_id}"


def _notify_pending(db: Session, tenant: TenantDescriptor, inst: WorkflowInstance, stage: dict[str, Any],
                    user_ids: list[int]) -> None:  # fmt: skip
    if not user_ids:
        return
    event = "approval.pending" if stage.get("kind", "APPROVE") == "APPROVE" else "review.pending"
    emit(
        db,
        tenant,
        event,
        user_ids,
        {
            "entity_label": ENTITY_TYPES[inst.entity_type].label,
            "title": inst.title,
            "stage": stage["name"],
            "submitted_by": _user_name(db, inst.submitted_by),
        },
        link=instance_link(inst),
        entity_type=inst.entity_type,
        entity_id=inst.entity_id,
    )


def _notify_submitter(db: Session, tenant: TenantDescriptor, inst: WorkflowInstance, event: str,
                      comment: str | None = None) -> None:  # fmt: skip
    emit(
        db,
        tenant,
        event,
        [inst.submitted_by],
        {"entity_label": ENTITY_TYPES[inst.entity_type].label, "title": inst.title, "comment": comment or ""},
        link=inst.link or instance_link(inst),
        entity_type=inst.entity_type,
        entity_id=inst.entity_id,
    )


def _stage_tasks(inst: WorkflowInstance, index: int | None = None) -> list[WorkflowTask]:
    idx = inst.stage_index if index is None else index
    return [t for t in inst.tasks if t.cycle == inst.cycle and t.stage_index == idx]


def _new_task(db: Session, inst: WorkflowInstance, idx: int, user_id: int, now: datetime, *,
              delegated_from: int | None = None, escalation: bool = False,
              due_at: datetime | None = None) -> WorkflowTask:  # fmt: skip
    stage = inst.stages[idx]
    sla = stage.get("sla_hours")
    t = WorkflowTask(
        instance=inst,
        cycle=inst.cycle,
        stage_index=idx,
        stage_name=stage["name"],
        assignee_id=user_id,
        delegated_from_id=delegated_from,
        is_escalation=escalation,
        due_at=due_at if due_at is not None else (now + timedelta(hours=int(sla)) if sla else None),
    )
    db.add(t)
    return t


# ============================================================================ lifecycle
def _start_stage(
    db: Session, tenant: TenantDescriptor, inst: WorkflowInstance, idx: int, now: datetime
) -> None:
    """Start stage ``idx``; skips optional stages without assignees; finishes after the last stage."""
    ctx = Context.from_json(inst.context)
    stages = inst.stages
    while idx < len(stages):
        stage = stages[idx]
        inst.stage_index = idx
        resolved = resolve_stage(db, inst.entity_type, stage, ctx, inst.submitted_by)
        if not resolved.assignees:
            if stage.get("optional"):
                _log(db, inst, "SKIP", None, stage_index=idx, comment="No approver for this stage")
                idx += 1
                continue
            raise ValidationFailed(
                f"Nobody can approve the stage “{stage['name']}”. "
                "Ask the administrator to check the workflow.",
                code="NO_APPROVER",
            )
        if resolved.fallback:
            _log(db, inst, "FALLBACK", None, stage_index=idx,
                 comment="No approver found; assigned to the parish administrators")  # fmt: skip
        for user_id, delegated_from in resolved.assignees:
            _new_task(db, inst, idx, user_id, now, delegated_from=delegated_from)
        db.flush()
        _notify_pending(db, tenant, inst, stage, [u for u, _ in resolved.assignees])
        return
    _finish(db, tenant, inst, "APPROVED", now)


def _finish(db: Session, tenant: TenantDescriptor, inst: WorkflowInstance, status: str, now: datetime,
            comment: str | None = None) -> None:  # fmt: skip
    inst.status = status
    inst.completed_at = now
    for t in inst.tasks:
        if t.status == "PENDING":
            t.status = "CANCELLED"
    h = handler_for(inst.entity_type)
    if status == "APPROVED":
        _log(db, inst, "COMPLETE", None, stage_index=len(inst.stages) - 1, prev="IN_PROGRESS")
        if h.on_approved:
            h.on_approved(db, inst)
        _notify_submitter(db, tenant, inst, "workflow.approved")
    elif status == "REJECTED":
        if h.on_rejected:
            h.on_rejected(db, inst)
        _notify_submitter(db, tenant, inst, "workflow.rejected", comment)


def active_instance(db: Session, entity_type: str, entity_id: str) -> WorkflowInstance | None:
    return db.scalar(
        select(WorkflowInstance).where(
            WorkflowInstance.entity_type == entity_type,
            WorkflowInstance.entity_id == entity_id,
            WorkflowInstance.status.in_(ACTIVE),
        )
    )


def submit(
    db: Session,
    tenant: TenantDescriptor,
    *,
    entity_type: str,
    entity_id: str,
    title: str,
    actor_id: int,
    org_unit_id: int | None = None,
    context: dict[str, Any] | None = None,
    link: str | None = None,
    comment: str | None = None,
) -> WorkflowInstance:
    """Start the approval of a record. Raises ``NO_WORKFLOW_CONFIGURED`` / ``ALREADY_SUBMITTED``."""
    if entity_type not in ENTITY_TYPES:
        raise ValidationFailed(f"Unknown workflow entity type {entity_type!r}")
    if active_instance(db, entity_type, entity_id) is not None:
        raise Conflict("This record is already in an approval workflow", code="ALREADY_SUBMITTED")
    ctx = Context.build(db, org_unit_id, context)
    defn = select_definition(db, entity_type, ctx)
    now = utcnow()
    inst = WorkflowInstance(
        definition_id=defn.id,
        snapshot=defn.snapshot(),
        entity_type=entity_type,
        entity_id=entity_id,
        title=title[:255],
        link=link,
        org_unit_id=org_unit_id,
        context=ctx.as_json(),
        status="IN_PROGRESS",
        cycle=1,
        stage_index=0,
        submitted_by=actor_id,
        submitted_at=now,
    )
    db.add(inst)
    db.flush()
    _log(db, inst, "SUBMIT", actor_id, stage_index=0, comment=comment)
    h = handler_for(entity_type)
    if h.on_submitted:
        h.on_submitted(db, inst)
    _start_stage(db, tenant, inst, 0, now)
    db.flush()
    return inst


def _lock(db: Session, inst_id: int) -> WorkflowInstance:
    inst = db.scalar(select(WorkflowInstance).where(WorkflowInstance.id == inst_id).with_for_update())
    if inst is None:
        raise NotFound("Workflow not found")
    db.refresh(inst)
    return inst


def act(
    db: Session,
    tenant: TenantDescriptor,
    task_public_id: str,
    actor_id: int,
    action: str,
    comment: str | None = None,
    *,
    delegate_to: int | None = None,
    override: bool = False,
) -> WorkflowInstance:
    """Record a reviewer's decision. ``override`` lets an administrator act on someone else's task."""
    action = action.upper()
    if action not in DECISIONS:
        raise ValidationFailed(f"Unknown action {action!r}")
    comment = (comment or "").strip() or None
    if action in ("REJECT", "RETURN") and not comment:
        raise ValidationFailed("Please give a reason", code="COMMENT_REQUIRED",
                               details=[{"field": "comment", "message": "Required"}])  # fmt: skip
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.public_id == task_public_id))
    if task is None:
        raise NotFound("Task not found")
    inst = _lock(db, task.instance_id)
    task = next(t for t in inst.tasks if t.id == task.id)
    if task.status != "PENDING" or inst.status != "IN_PROGRESS":
        raise Conflict("This task has already been completed", code="TASK_NOT_PENDING")
    on_behalf: int | None = None
    if task.assignee_id != actor_id:
        if not override:
            raise PermissionDenied("This task is assigned to someone else", code="NOT_ASSIGNEE")
        on_behalf = task.assignee_id
    stage = inst.stages[task.stage_index]
    now = utcnow()
    prev = inst.status
    task.acted_at, task.acted_by, task.comment = now, actor_id, comment

    if action == "DELEGATE":
        if stage.get("allow_delegation", True) is False:
            raise ValidationFailed("Delegation is not allowed at this stage", code="DELEGATION_NOT_ALLOWED")
        delegate = db.get(User, delegate_to) if delegate_to else None
        if delegate is None or not delegate.is_active or delegate.is_deleted:
            raise ValidationFailed("Choose an active user to delegate to", code="INVALID_DELEGATE")
        if delegate.id == inst.submitted_by and not _setting(db, "workflow.allow_self_approval", False):
            raise ValidationFailed("The submitter cannot approve their own record", code="SELF_APPROVAL")
        if any(t.assignee_id == delegate.id and t.status == "PENDING" for t in _stage_tasks(inst)):
            raise Conflict("This person already has this task", code="ALREADY_ASSIGNED")
        task.status = "DELEGATED"
        new = _new_task(db, inst, task.stage_index, delegate.id, now, delegated_from=task.assignee_id,
                        escalation=task.is_escalation, due_at=task.due_at)  # fmt: skip
        db.flush()
        _log(db, inst, "DELEGATE", actor_id, task=task, prev=prev, on_behalf_of=on_behalf,
             comment=f"{comment + ' — ' if comment else ''}to {delegate.full_name}")  # fmt: skip
        _notify_pending(db, tenant, inst, stage, [new.assignee_id])
        return inst

    if action == "APPROVE":
        task.status = "APPROVED"
        _log(db, inst, "APPROVE", actor_id, task=task, comment=comment, prev=prev, on_behalf_of=on_behalf)
        if _stage_complete(inst, stage, task):
            for t in _stage_tasks(inst):
                if t.status == "PENDING":
                    t.status = "CANCELLED"
            _start_stage(db, tenant, inst, task.stage_index + 1, now)
    elif action == "REJECT":
        task.status = "REJECTED"
        _finish(db, tenant, inst, "REJECTED", now, comment)
        _log(db, inst, "REJECT", actor_id, task=task, comment=comment, prev=prev, on_behalf_of=on_behalf)
    else:  # RETURN
        task.status = "RETURNED"
        inst.status = "REWORK"
        for t in inst.tasks:
            if t.status == "PENDING":
                t.status = "CANCELLED"
        _log(db, inst, "RETURN", actor_id, task=task, comment=comment, prev=prev, on_behalf_of=on_behalf)
        h = handler_for(inst.entity_type)
        if h.on_rework:
            h.on_rework(db, inst)
        _notify_submitter(db, tenant, inst, "workflow.returned", comment)
    db.flush()
    return inst


def _stage_complete(inst: WorkflowInstance, stage: dict[str, Any], task: WorkflowTask) -> bool:
    if task.is_escalation:
        return True  # escalation approvers decide the stage on their own
    tasks = [t for t in _stage_tasks(inst, task.stage_index) if not t.is_escalation]
    pool = [t for t in tasks if t.status not in ("DELEGATED", "CANCELLED")]
    approved = sum(t.status == "APPROVED" for t in pool)
    quorum = stage.get("quorum", "ANY")
    if quorum == "ALL":
        need = len(pool)
    elif quorum == "ANY":
        need = 1
    else:
        need = min(int(quorum), len(pool))
    return approved >= max(need, 1)


def resubmit(
    db: Session,
    tenant: TenantDescriptor,
    inst: WorkflowInstance,
    actor_id: int,
    comment: str | None = None,
    *,
    title: str | None = None,
    context: dict[str, Any] | None = None,
) -> WorkflowInstance:
    """Send a returned record back for approval: a new cycle starting at the first stage (same
    definition snapshot)."""
    inst = _lock(db, inst.id)
    if inst.status != "REWORK":
        raise Conflict("Only records returned for rework can be resubmitted", code="INVALID_STATE")
    if actor_id != inst.submitted_by:
        raise PermissionDenied("Only the submitter can resubmit", code="NOT_SUBMITTER")
    if title:
        inst.title = title[:255]
    if context is not None:
        inst.context = Context.build(db, inst.org_unit_id, context).as_json()
    prev = inst.status
    inst.cycle += 1
    inst.status = "IN_PROGRESS"
    inst.stage_index = 0
    _log(db, inst, "RESUBMIT", actor_id, stage_index=0, comment=comment, prev=prev)
    h = handler_for(inst.entity_type)
    if h.on_submitted:
        h.on_submitted(db, inst)
    _start_stage(db, tenant, inst, 0, utcnow())
    db.flush()
    return inst


def withdraw(
    db: Session, tenant: TenantDescriptor, inst: WorkflowInstance, actor_id: int, comment: str | None = None
) -> WorkflowInstance:
    inst = _lock(db, inst.id)
    if inst.status not in ACTIVE:
        raise Conflict("This approval has already finished", code="INVALID_STATE")
    if actor_id != inst.submitted_by:
        raise PermissionDenied("Only the submitter can withdraw", code="NOT_SUBMITTER")
    prev = inst.status
    inst.status = "CANCELLED"
    inst.completed_at = utcnow()
    for t in inst.tasks:
        if t.status == "PENDING":
            t.status = "CANCELLED"
    _log(db, inst, "WITHDRAW", actor_id, comment=comment, prev=prev)
    h = handler_for(inst.entity_type)
    if h.on_withdrawn:
        h.on_withdrawn(db, inst)
    db.flush()
    return inst


# ============================================================================ SLA
def process_overdue(db: Session, tenant: TenantDescriptor, now: datetime | None = None) -> dict[str, int]:
    """Remind assignees of overdue tasks (once per SLA period) and escalate once per stage."""
    now = now or utcnow()
    reminded = escalated = 0
    overdue = db.scalars(
        select(WorkflowTask)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowTask.instance_id)
        .where(
            WorkflowTask.status == "PENDING",
            WorkflowTask.due_at.is_not(None),
            WorkflowTask.due_at < now,
            WorkflowInstance.status == "IN_PROGRESS",
        )
        .order_by(WorkflowTask.id)
    ).all()
    for task in overdue:
        inst = task.instance
        stage = inst.stages[task.stage_index]
        sla = timedelta(hours=int(stage.get("sla_hours") or 24))
        if task.reminded_at is None or task.reminded_at <= now - sla:
            emit(
                db,
                tenant,
                "workflow.reminder",
                [task.assignee_id],
                {
                    "entity_label": ENTITY_TYPES[inst.entity_type].label,
                    "title": inst.title,
                    "stage": stage["name"],
                },
                link=instance_link(inst),
                entity_type=inst.entity_type,
                entity_id=inst.entity_id,
            )
            task.reminded_at = now
            reminded += 1
        if stage.get("escalate_to") and not task.escalated and not task.is_escalation:
            stage_tasks = _stage_tasks(inst, task.stage_index)
            for t in stage_tasks:
                if not t.is_escalation:
                    t.escalated = True
            if any(t.is_escalation for t in stage_tasks):
                continue
            ctx = Context.from_json(inst.context)
            users: set[int] = set()
            for rule in stage["escalate_to"]:
                users |= resolve_rule(db, rule, ctx)
            users -= {t.assignee_id for t in stage_tasks if t.status == "PENDING"} | {inst.submitted_by}
            if not users:
                continue
            for u in sorted(users):
                _new_task(db, inst, task.stage_index, u, now, escalation=True)
            db.flush()
            names = ", ".join(_user_name(db, u) for u in sorted(users))
            _log(db, inst, "ESCALATE", None, task=task, comment=f"Overdue; escalated to {names}")
            _notify_pending(db, tenant, inst, stage, sorted(users))
            escalated += 1
    db.flush()
    return {"reminded": reminded, "escalated": escalated}


# ============================================================================ preview
def preview(
    db: Session, entity_type: str, org_unit_id: int | None, context: dict[str, Any] | None,
    submitter_id: int | None, definition: WorkflowDefinition | None = None,
) -> dict[str, Any]:  # fmt: skip
    """Who would approve such a record right now (no data is written)."""
    ctx = Context.build(db, org_unit_id, context)
    defn = definition or select_definition(db, entity_type, ctx)
    stages = []
    for i, stage in enumerate(defn.stages):
        r = resolve_stage(db, entity_type, stage, ctx, submitter_id)
        stages.append(
            {
                "index": i,
                "name": stage["name"],
                "quorum": str(stage.get("quorum", "ANY")),
                "skipped": not r.assignees and bool(stage.get("optional")),
                "fallback": r.fallback,
                "assignees": [
                    {"name": _user_name(db, u), "delegated_from": _user_name(db, f) if f else None}
                    for u, f in r.assignees
                ],
            }
        )
    return {"definition": defn, "stages": stages}


# ============================================================================ visibility
def involved_user_ids(inst: WorkflowInstance) -> set[int]:
    return (
        {inst.submitted_by}
        | {t.assignee_id for t in inst.tasks}
        | {t.delegated_from_id for t in inst.tasks if t.delegated_from_id}
    )


def visible_instances_clause(user_id: int) -> Any:
    sub = select(WorkflowTask.instance_id).where(
        or_(WorkflowTask.assignee_id == user_id, WorkflowTask.delegated_from_id == user_id)
    )
    return or_(WorkflowInstance.submitted_by == user_id, WorkflowInstance.id.in_(sub))

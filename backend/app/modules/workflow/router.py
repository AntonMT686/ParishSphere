"""Approval workflows (``/api/v1/workflow``): configuration, My Approvals inbox, timelines, delegations."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import record_audit
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.core.errors import AppError, NotFound, PermissionDenied, ValidationFailed
from app.db.base import utcnow
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.org_units.models import OrgUnit, OrgUnitPosition
from app.modules.rbac.deps import require_perm
from app.modules.rbac.models import Role
from app.modules.rbac.service import PermissionScope
from app.modules.workflow import service as svc
from app.modules.workflow.models import (
    WorkflowDefinition,
    WorkflowDelegation,
    WorkflowInstance,
    WorkflowTask,
)
from app.modules.workflow.registry import ENTITY_TYPES
from app.modules.workflow.schemas import (
    ActIn,
    ActionOut,
    BulkApproveIn,
    BulkResult,
    CommentIn,
    DefinitionIn,
    DefinitionOut,
    DefinitionUpdate,
    DelegationIn,
    DelegationOut,
    EntityTypeOut,
    InstanceDetail,
    InstanceSummary,
    PreviewIn,
    PreviewOut,
    StageIn,
    StageState,
    TaskBrief,
    TaskOut,
    TaskSummaryOut,
    WorkflowRef,
)
from app.tenancy.deps import TenantSession

router = APIRouter(prefix="/workflow", tags=["workflow"])
MODULE = "workflow"

CanView = Annotated[PermissionScope, Depends(require_perm("workflow.view", parish_wide=True))]
CanManage = Annotated[PermissionScope, Depends(require_perm("workflow.manage", parish_wide=True))]


# ============================================================================ helpers
class Users:
    """Batch-friendly user id → WorkflowRef lookup for one response."""

    def __init__(self, db: Session) -> None:
        self.db, self.cache = db, {}  # type: ignore[var-annotated]

    def ref(self, user_id: int | None) -> WorkflowRef | None:
        if user_id is None:
            return None
        if user_id not in self.cache:
            u = self.db.get(User, user_id)
            self.cache[user_id] = (
                WorkflowRef(id=u.public_id, name=u.full_name) if u else WorkflowRef(id="", name="—")
            )
        return self.cache[user_id]


def _user_id(db: Session, public_id: str | None) -> int | None:
    if not public_id:
        return None
    uid = db.scalar(select(User.id).where(User.public_id == public_id, User.is_deleted.is_(False)))
    if uid is None:
        raise NotFound("User not found")
    return uid


def _org_unit_id(db: Session, public_id: str | None) -> int | None:
    if not public_id:
        return None
    uid = db.scalar(select(OrgUnit.id).where(OrgUnit.public_id == public_id, OrgUnit.is_deleted.is_(False)))
    if uid is None:
        raise NotFound("Organisation not found")
    return uid


def _entity_type(code: str) -> str:
    if code not in ENTITY_TYPES:
        raise ValidationFailed(details=[{"field": "entity_type", "message": f"Unknown type {code!r}"}])
    return code


_SCOPE_LABEL = {
    "PARISH": "",
    "SAME_ORG_UNIT": " of the record's organisation",
    "PARENT_ORG_UNIT": " of the parent organisation",
}


def _rule_label(db: Session, rule: dict[str, Any]) -> str:
    if rule["type"] == "USER":
        u = db.scalar(select(User).where(User.public_id == rule.get("user_id")))
        return u.full_name if u else "Unknown user"
    if rule["type"] == "ROLE":
        name = db.scalar(select(Role.name).where(Role.code == rule["role"])) or rule["role"]
        return f"{name}{_SCOPE_LABEL[rule.get('scope', 'PARISH')]}" + (
            " (parish-wide)" if rule.get("scope", "PARISH") == "PARISH" else ""
        )
    name = db.scalar(select(OrgUnitPosition.name).where(OrgUnitPosition.code == rule["position"]).limit(1))
    return f"{name or rule['position']}{_SCOPE_LABEL[rule['scope']]}"


def _validate_stages(db: Session, stages: list[StageIn]) -> list[dict[str, Any]]:
    roles = set(db.scalars(select(Role.code).where(Role.is_deleted.is_(False))))
    positions = set(db.scalars(select(OrgUnitPosition.code).where(OrgUnitPosition.is_deleted.is_(False))))
    out: list[dict[str, Any]] = []
    keys: set[str] = set()
    for i, st in enumerate(stages):
        data = st.model_dump()
        key = data.get("key") or f"stage_{i + 1}"
        while key in keys:
            key += "_"
        keys.add(key)
        data["key"] = key
        for field in ("assignees", "escalate_to"):
            for j, rule in enumerate(data[field]):
                loc = f"stages[{i}].{field}[{j}]"
                if rule["type"] == "ROLE" and rule["role"] not in roles:
                    raise ValidationFailed(
                        details=[{"field": loc, "message": f"Unknown role {rule['role']}"}]
                    )
                if rule["type"] == "POSITION" and rule["position"] not in positions:
                    raise ValidationFailed(
                        details=[{"field": loc, "message": f"Unknown position {rule['position']}"}]
                    )
                if rule["type"] == "USER":
                    _user_id(db, rule["user_id"])
                data[field][j] = {k: v for k, v in rule.items() if v is not None}
        out.append(data)
    return out


def _definition_out(db: Session, d: WorkflowDefinition) -> DefinitionOut:
    running = db.scalar(
        select(func.count())
        .select_from(WorkflowInstance)
        .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowInstance.definition_id)
        .where(WorkflowDefinition.code == d.code, WorkflowInstance.status.in_(svc.ACTIVE))
    )
    stages = []
    for s in d.stages:
        stages.append(
            {
                **s,
                "assignees": [{**r, "label": _rule_label(db, r)} for r in s.get("assignees", [])],
                "escalate_to": [{**r, "label": _rule_label(db, r)} for r in s.get("escalate_to", [])],
            }
        )
    return DefinitionOut(
        id=d.public_id,
        code=d.code,
        version=d.version,
        is_latest=d.is_latest,
        is_active=d.is_active,
        entity_type=d.entity_type,
        entity_label=ENTITY_TYPES[d.entity_type].label if d.entity_type in ENTITY_TYPES else d.entity_type,
        name=d.name,
        description=d.description,
        priority=d.priority,
        conditions=d.conditions or {},
        stages=stages,
        is_system=d.is_system,
        running=running or 0,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _get_definition(db: Session, public_id: str) -> WorkflowDefinition:
    d = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.public_id == public_id, WorkflowDefinition.is_deleted.is_(False)
        )
    )
    if d is None:
        raise NotFound("Workflow not found")
    return d


def _summary(db: Session, inst: WorkflowInstance, users: Users) -> InstanceSummary:
    stages = inst.stages
    unit = db.get(OrgUnit, inst.org_unit_id) if inst.org_unit_id else None
    pending = [t for t in inst.tasks if t.status == "PENDING"]
    return InstanceSummary(
        id=inst.public_id,
        entity_type=inst.entity_type,
        entity_label=ENTITY_TYPES[inst.entity_type].label,
        entity_id=inst.entity_id,
        title=inst.title,
        link=inst.link,
        org_unit=WorkflowRef(id=unit.public_id, name=unit.name) if unit else None,
        amount=inst.context.get("amount"),
        category=inst.context.get("category"),
        status=inst.status,
        cycle=inst.cycle,
        stage_index=inst.stage_index,
        stage_name=stages[inst.stage_index]["name"] if inst.stage_index < len(stages) else None,
        stage_count=len(stages),
        pending_with=[users.ref(t.assignee_id).name for t in pending],  # type: ignore[union-attr]
        submitted_by=users.ref(inst.submitted_by),  # type: ignore[arg-type]
        submitted_at=inst.submitted_at,
        completed_at=inst.completed_at,
    )


def _brief(t: WorkflowTask, users: Users) -> TaskBrief:
    return TaskBrief(
        id=t.public_id,
        assignee=users.ref(t.assignee_id),  # type: ignore[arg-type]
        delegated_from=users.ref(t.delegated_from_id),
        status=t.status,
        is_escalation=t.is_escalation,
        due_at=t.due_at,
        acted_at=t.acted_at,
        acted_by=users.ref(t.acted_by) if t.acted_by and t.acted_by != t.assignee_id else None,
        comment=t.comment,
    )


def _can_view(auth: Auth, inst: WorkflowInstance) -> bool:
    if auth.user.id in svc.involved_user_ids(inst):
        return True
    perms = auth.permissions
    if perms.scope("workflow.view").parish_wide:
        return True
    return perms.scope(f"{ENTITY_TYPES[inst.entity_type].module}.view").allows(inst.org_unit_id)


def _detail(db: Session, auth: Auth, inst: WorkflowInstance) -> InstanceDetail:
    users = Users(db)
    stages = inst.stages
    skipped = {a.stage_index for a in inst.actions if a.cycle == inst.cycle and a.action == "SKIP"}
    states: list[StageState] = []
    for i, st in enumerate(stages):
        tasks = [t for t in inst.tasks if t.cycle == inst.cycle and t.stage_index == i]
        if i in skipped:
            state = "SKIPPED"
        elif inst.status == "APPROVED" or i < inst.stage_index:
            state = "DONE"
        elif i == inst.stage_index and inst.status in ("IN_PROGRESS", "REWORK", "REJECTED"):
            state = "CURRENT"
        else:
            state = "UPCOMING"
        states.append(
            StageState(
                index=i,
                name=st["name"],
                kind=st.get("kind", "REVIEW"),
                quorum=str(st.get("quorum", "ANY")),
                optional=bool(st.get("optional")),
                state=state,  # type: ignore[arg-type]
                tasks=[_brief(t, users) for t in tasks],
            )
        )
    actions = [
        ActionOut(
            id=a.id,
            action=a.action,
            actor=users.ref(a.actor_id),
            on_behalf_of=users.ref(a.on_behalf_of_id),
            comment=a.comment,
            cycle=a.cycle,
            stage_name=a.stage_name,
            prev_status=a.prev_status,
            new_status=a.new_status,
            created_at=a.created_at,
        )
        for a in inst.actions
    ]
    mine = next((t for t in inst.tasks if t.status == "PENDING" and t.assignee_id == auth.user.id), None)
    snap = inst.snapshot
    return InstanceDetail(
        **_summary(db, inst, users).model_dump(),
        definition={
            "code": snap.get("code", ""),
            "version": snap.get("version", 1),
            "name": snap.get("name", ""),
        },
        stages=states,
        actions=actions,
        my_task=mine.public_id if mine else None,
        can_withdraw=inst.submitted_by == auth.user.id and inst.status in svc.ACTIVE,
        can_resubmit=inst.submitted_by == auth.user.id and inst.status == "REWORK",
        can_override=auth.permissions.scope("workflow.manage").parish_wide and inst.status == "IN_PROGRESS",
    )


def _get_instance(db: Session, public_id: str) -> WorkflowInstance:
    inst = db.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == public_id))
    if inst is None:
        raise NotFound("Approval not found")
    return inst


# ============================================================================ configuration
@router.get("/entity-types", response_model=list[EntityTypeOut])
def entity_types(_: CanView, db: TenantSession) -> list[EntityTypeOut]:
    counts = dict(
        db.execute(
            select(WorkflowDefinition.entity_type, func.count())
            .where(WorkflowDefinition.is_latest.is_(True), WorkflowDefinition.is_deleted.is_(False))
            .group_by(WorkflowDefinition.entity_type)
        ).all()
    )
    return [
        EntityTypeOut(
            code=e.code,
            label=e.label,
            has_amount=e.has_amount,
            has_category=e.has_category,
            definitions=counts.get(e.code, 0),
        )  # fmt: skip
        for e in ENTITY_TYPES.values()
    ]


@router.get("/definitions", response_model=list[DefinitionOut])
def list_definitions(
    _: CanView,
    db: TenantSession,
    entity_type: Annotated[str | None, Query(max_length=30)] = None,
    code: Annotated[str | None, Query(max_length=50, description="All versions of one workflow")] = None,
) -> list[DefinitionOut]:
    stmt = select(WorkflowDefinition).where(WorkflowDefinition.is_deleted.is_(False))
    if code:
        stmt = stmt.where(WorkflowDefinition.code == code).order_by(WorkflowDefinition.version.desc())
    else:
        stmt = stmt.where(WorkflowDefinition.is_latest.is_(True)).order_by(
            WorkflowDefinition.entity_type, WorkflowDefinition.priority.desc(), WorkflowDefinition.name
        )
    if entity_type:
        stmt = stmt.where(WorkflowDefinition.entity_type == entity_type)
    return [_definition_out(db, d) for d in db.scalars(stmt)]


@router.get("/definitions/{definition_id}", response_model=DefinitionOut)
def get_definition(definition_id: str, _: CanView, db: TenantSession) -> DefinitionOut:
    return _definition_out(db, _get_definition(db, definition_id))


def _next_code(db: Session, entity_type: str) -> str:
    base = f"{entity_type}_CUSTOM"
    n = db.scalar(select(func.count(func.distinct(WorkflowDefinition.code))).where(
        WorkflowDefinition.code.like(f"{base}%")))  # fmt: skip
    code = f"{base}_{(n or 0) + 1}"
    while db.scalar(select(WorkflowDefinition.id).where(WorkflowDefinition.code == code).limit(1)):
        n = (n or 0) + 1
        code = f"{base}_{n + 1}"
    return code


@router.post("/definitions", response_model=DefinitionOut, status_code=status.HTTP_201_CREATED)
def create_definition(
    body: DefinitionIn, request: Request, auth: Auth, _: CanManage, db: TenantSession
) -> DefinitionOut:
    etype = _entity_type(body.entity_type)
    d = WorkflowDefinition(
        code=_next_code(db, etype),
        version=1,
        is_latest=True,
        is_active=True,
        entity_type=etype,
        name=body.name.strip(),
        description=body.description,
        priority=body.priority,
        conditions=body.conditions.model_dump(exclude_none=True),
        stages=_validate_stages(db, body.stages),
        created_by=auth.user.id,
    )
    db.add(d)
    db.flush()
    record_audit(db, action="CREATE", module=MODULE, user_id=auth.user.id, request=request,
                 entity_type="workflow_definition", entity_id=d.code, new=d.snapshot())  # fmt: skip
    return _definition_out(db, d)


@router.put("/definitions/{definition_id}", response_model=DefinitionOut)
def new_version(
    definition_id: str, body: DefinitionUpdate, request: Request, auth: Auth, _: CanManage, db: TenantSession
) -> DefinitionOut:
    """Save changes as a new version. Approvals already running keep the version they started with."""
    old = _get_definition(db, definition_id)
    if not old.is_latest:
        raise ValidationFailed("Only the latest version can be edited", code="NOT_LATEST_VERSION")
    old.is_latest = False
    d = WorkflowDefinition(
        code=old.code,
        version=old.version + 1,
        is_latest=True,
        is_active=old.is_active,
        entity_type=old.entity_type,
        name=body.name.strip(),
        description=body.description,
        priority=body.priority,
        conditions=body.conditions.model_dump(exclude_none=True),
        stages=_validate_stages(db, body.stages),
        is_system=old.is_system,
        created_by=auth.user.id,
    )
    db.add(d)
    db.flush()
    record_audit(db, action="NEW_VERSION", module=MODULE, user_id=auth.user.id, request=request,
                 entity_type="workflow_definition", entity_id=d.code,
                 old=old.snapshot(), new=d.snapshot())  # fmt: skip
    return _definition_out(db, d)


@router.post("/definitions/{definition_id}/{state}", response_model=DefinitionOut)
def set_active(
    definition_id: str, state: str, request: Request, auth: Auth, _: CanManage, db: TenantSession
) -> DefinitionOut:
    if state not in ("activate", "deactivate"):
        raise NotFound()
    d = _get_definition(db, definition_id)
    if not d.is_latest:
        raise ValidationFailed("Only the latest version can be switched on or off", code="NOT_LATEST_VERSION")
    d.is_active = state == "activate"
    d.updated_by = auth.user.id
    record_audit(db, action=state.upper(), module=MODULE, user_id=auth.user.id, request=request,
                 entity_type="workflow_definition", entity_id=d.code)  # fmt: skip
    return _definition_out(db, d)


@router.post("/preview", response_model=PreviewOut)
def preview(body: PreviewIn, _: CanView, auth: Auth, db: TenantSession) -> PreviewOut:
    """Who would approve such a record now – for the selected workflow or for unsaved stages."""
    etype = _entity_type(body.entity_type)
    draft = None
    if body.stages:
        draft = WorkflowDefinition(code="DRAFT", version=0, name="Draft", entity_type=etype,
                                   stages=_validate_stages(db, body.stages))  # fmt: skip
    res = svc.preview(
        db,
        etype,
        _org_unit_id(db, body.org_unit_id),
        {"amount": body.amount, "category": body.category},
        _user_id(db, body.submitter_user_id),
        definition=draft,
    )
    d = res["definition"]
    return PreviewOut(
        definition=None
        if draft
        else {"id": d.public_id, "code": d.code, "name": d.name, "version": d.version},
        stages=res["stages"],
    )


# ============================================================================ inbox
def _task_out(db: Session, t: WorkflowTask, users: Users, now: Any) -> TaskOut:
    inst = t.instance
    stage = inst.stages[t.stage_index] if t.stage_index < len(inst.stages) else {}
    return TaskOut(
        id=t.public_id,
        status=t.status,
        stage_index=t.stage_index,
        stage_name=t.stage_name,
        kind=stage.get("kind", "REVIEW"),
        is_escalation=t.is_escalation,
        delegated_from=users.ref(t.delegated_from_id),
        due_at=t.due_at,
        overdue=bool(t.status == "PENDING" and t.due_at and t.due_at < now),
        created_at=t.created_at,
        acted_at=t.acted_at,
        comment=t.comment,
        instance=_summary(db, inst, users),
    )


@router.get("/tasks", response_model=Page[TaskOut])
def my_tasks(
    auth: Auth,
    db: TenantSession,
    params: PageQuery,
    state: Annotated[str, Query(pattern="^(PENDING|DONE)$")] = "PENDING",
    entity_type: Annotated[str | None, Query(max_length=30)] = None,
    overdue: bool | None = None,
) -> Page[TaskOut]:
    """My Approvals: tasks assigned to me (pending) or decided by me (done)."""
    now = utcnow()
    stmt = (
        select(WorkflowTask)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowTask.instance_id)
        .where(WorkflowTask.assignee_id == auth.user.id)
    )
    if state == "PENDING":
        stmt = stmt.where(WorkflowTask.status == "PENDING", WorkflowInstance.status == "IN_PROGRESS")
    else:
        stmt = stmt.where(WorkflowTask.status.in_(("APPROVED", "REJECTED", "RETURNED", "DELEGATED")))
    if entity_type:
        stmt = stmt.where(WorkflowInstance.entity_type == entity_type)
    if overdue:
        stmt = stmt.where(WorkflowTask.due_at.is_not(None), WorkflowTask.due_at < now)
    stmt = apply_sort(
        stmt,
        params.sort,
        {
            "created_at": WorkflowTask.created_at,
            "due_at": WorkflowTask.due_at,
            "acted_at": WorkflowTask.acted_at,
        },
        [WorkflowTask.created_at.desc() if state == "DONE" else WorkflowTask.created_at, WorkflowTask.id],
    )
    users = Users(db)
    return paginate(db, stmt, params, lambda t: _task_out(db, t, users, now))


@router.get("/tasks/summary", response_model=TaskSummaryOut)
def task_summary(auth: Auth, db: TenantSession) -> TaskSummaryOut:
    now = utcnow()
    base = (
        select(func.count())
        .select_from(WorkflowTask)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowTask.instance_id)
        .where(
            WorkflowTask.assignee_id == auth.user.id,
            WorkflowTask.status == "PENDING",
            WorkflowInstance.status == "IN_PROGRESS",
        )
    )
    return TaskSummaryOut(
        pending=db.scalar(base) or 0,
        overdue=db.scalar(base.where(WorkflowTask.due_at.is_not(None), WorkflowTask.due_at < now)) or 0,
    )


@router.post("/tasks/{task_id}/act", response_model=InstanceDetail)
def act(task_id: str, body: ActIn, request: Request, auth: Auth, db: TenantSession) -> InstanceDetail:
    override = auth.permissions.scope("workflow.manage").parish_wide
    inst = svc.act(
        db,
        auth.tenant,
        task_id,
        auth.user.id,
        body.action,
        body.comment,
        delegate_to=_user_id(db, body.delegate_user_id) if body.action == "DELEGATE" else None,
        override=override,
    )
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.public_id == task_id))
    if task is not None and task.acted_by == auth.user.id and task.assignee_id != auth.user.id:
        record_audit(db, action="OVERRIDE", module=MODULE, user_id=auth.user.id, request=request,
                     entity_type="workflow_task", entity_id=task_id,
                     remarks=f"{body.action} on behalf of user {task.assignee_id}")  # fmt: skip
    return _detail(db, auth, inst)


@router.post("/tasks/bulk-approve", response_model=BulkResult)
def bulk_approve(body: BulkApproveIn, auth: Auth, db: TenantSession) -> BulkResult:
    """Approve several of my own pending tasks; each is decided independently."""
    approved: list[str] = []
    failed: list[dict[str, str]] = []
    for tid in dict.fromkeys(body.task_ids):
        sp = db.begin_nested()
        try:
            svc.act(db, auth.tenant, tid, auth.user.id, "APPROVE", body.comment)
            sp.commit()
            approved.append(tid)
        except AppError as exc:
            sp.rollback()
            failed.append({"id": tid, "code": exc.code, "message": exc.message})
    return BulkResult(approved=approved, failed=failed)


# ============================================================================ instances
@router.get("/instances", response_model=Page[InstanceSummary])
def list_instances(
    auth: Auth,
    db: TenantSession,
    params: PageQuery,
    mine: bool = True,
    status_: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    entity_type: Annotated[str | None, Query(max_length=30)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[InstanceSummary]:
    """Submitted by me (default) or, with ``mine=false``, every approval (needs workflow.view)."""
    stmt = select(WorkflowInstance)
    if mine:
        stmt = stmt.where(WorkflowInstance.submitted_by == auth.user.id)
    elif not auth.permissions.scope("workflow.view").parish_wide:
        raise PermissionDenied(details=[{"field": "permission", "message": "workflow.view"}])
    if status_ == "ACTIVE":
        stmt = stmt.where(WorkflowInstance.status.in_(svc.ACTIVE))
    elif status_:
        stmt = stmt.where(WorkflowInstance.status == status_)
    if entity_type:
        stmt = stmt.where(WorkflowInstance.entity_type == entity_type)
    if q:
        stmt = stmt.where(WorkflowInstance.title.ilike(f"%{q.strip()}%"))
    stmt = apply_sort(
        stmt,
        params.sort,
        {
            "submitted_at": WorkflowInstance.submitted_at,
            "title": WorkflowInstance.title,
            "updated_at": WorkflowInstance.updated_at,
        },  # fmt: skip
        [WorkflowInstance.updated_at.desc(), WorkflowInstance.id.desc()],
    )
    users = Users(db)
    return paginate(db, stmt, params, lambda i: _summary(db, i, users))


@router.get("/instances/{instance_id}", response_model=InstanceDetail)
def get_instance(instance_id: str, auth: Auth, db: TenantSession) -> InstanceDetail:
    inst = _get_instance(db, instance_id)
    if not _can_view(auth, inst):
        raise PermissionDenied("You cannot view this approval")
    return _detail(db, auth, inst)


@router.get("/entities/{entity_type}/{entity_id}", response_model=list[InstanceDetail])
def entity_history(entity_type: str, entity_id: str, auth: Auth, db: TenantSession) -> list[InstanceDetail]:
    """Every approval run of one record, newest first (for the ApprovalTimeline component)."""
    rows = db.scalars(
        select(WorkflowInstance)
        .where(
            WorkflowInstance.entity_type == _entity_type(entity_type), WorkflowInstance.entity_id == entity_id
        )
        .order_by(WorkflowInstance.id.desc())
    ).all()
    return [_detail(db, auth, i) for i in rows if _can_view(auth, i)]


@router.post("/instances/{instance_id}/withdraw", response_model=InstanceDetail)
def withdraw(instance_id: str, body: CommentIn, auth: Auth, db: TenantSession) -> InstanceDetail:
    inst = svc.withdraw(db, auth.tenant, _get_instance(db, instance_id), auth.user.id, body.comment)
    return _detail(db, auth, inst)


@router.post("/instances/{instance_id}/resubmit", response_model=InstanceDetail)
def resubmit(instance_id: str, body: CommentIn, auth: Auth, db: TenantSession) -> InstanceDetail:
    inst = svc.resubmit(db, auth.tenant, _get_instance(db, instance_id), auth.user.id, body.comment)
    return _detail(db, auth, inst)


# ============================================================================ delegations
def _delegation_out(d: WorkflowDelegation, users: Users) -> DelegationOut:
    return DelegationOut(
        id=d.public_id,
        delegator=users.ref(d.delegator_id),  # type: ignore[arg-type]
        delegate=users.ref(d.delegate_id),  # type: ignore[arg-type]
        valid_from=d.valid_from,
        valid_to=d.valid_to,
        entity_types=d.entity_types,
        reason=d.reason,
        active=d.is_active_on(date.today()),
        ended_at=d.ended_at,
    )


@router.get("/delegations", response_model=list[DelegationOut])
def list_delegations(
    auth: Auth, db: TenantSession, all_users: Annotated[bool, Query(alias="all")] = False
) -> list[DelegationOut]:
    stmt = select(WorkflowDelegation).order_by(WorkflowDelegation.id.desc())
    if all_users:
        if not auth.permissions.scope("workflow.manage").parish_wide:
            raise PermissionDenied(details=[{"field": "permission", "message": "workflow.manage"}])
    else:
        stmt = stmt.where(
            or_(
                WorkflowDelegation.delegator_id == auth.user.id,
                WorkflowDelegation.delegate_id == auth.user.id,
            )
        )
    users = Users(db)
    return [_delegation_out(d, users) for d in db.scalars(stmt.limit(200))]


@router.post("/delegations", response_model=DelegationOut, status_code=status.HTTP_201_CREATED)
def create_delegation(body: DelegationIn, request: Request, auth: Auth, db: TenantSession) -> DelegationOut:
    delegator = auth.user.id
    if body.delegator_user_id:
        delegator = _user_id(db, body.delegator_user_id)  # type: ignore[assignment]
        if delegator != auth.user.id and not auth.permissions.scope("workflow.manage").parish_wide:
            raise PermissionDenied("Only administrators can set up delegations for others")
    delegate = _user_id(db, body.delegate_user_id)
    if delegate == delegator:
        raise ValidationFailed("You cannot delegate to yourself", code="INVALID_DELEGATE")
    du = db.get(User, delegate)
    if du is None or not du.is_active:
        raise ValidationFailed("Choose an active user to delegate to", code="INVALID_DELEGATE")
    for et in body.entity_types or []:
        _entity_type(et)
    d = WorkflowDelegation(
        delegator_id=delegator,
        delegate_id=delegate,
        valid_from=body.valid_from or date.today(),
        valid_to=body.valid_to,
        entity_types=body.entity_types or None,
        reason=body.reason,
        created_by=auth.user.id,
    )
    db.add(d)
    db.flush()
    record_audit(db, action="DELEGATE", module=MODULE, user_id=auth.user.id, request=request,
                 entity_type="workflow_delegation", entity_id=d.public_id,
                 new={"delegator": delegator, "delegate": delegate, "valid_from": str(d.valid_from),
                      "valid_to": str(d.valid_to) if d.valid_to else None})  # fmt: skip
    return _delegation_out(d, Users(db))


@router.post("/delegations/{delegation_id}/end", response_model=DelegationOut)
def end_delegation(delegation_id: str, request: Request, auth: Auth, db: TenantSession) -> DelegationOut:
    d = db.scalar(select(WorkflowDelegation).where(WorkflowDelegation.public_id == delegation_id))
    if d is None:
        raise NotFound("Delegation not found")
    if d.delegator_id != auth.user.id and not auth.permissions.scope("workflow.manage").parish_wide:
        raise PermissionDenied("You cannot end this delegation")
    if d.ended_at is None:
        d.ended_at, d.ended_by = utcnow(), auth.user.id
        record_audit(db, action="END_DELEGATION", module=MODULE, user_id=auth.user.id, request=request,
                     entity_type="workflow_delegation", entity_id=d.public_id)  # fmt: skip
    return _delegation_out(d, Users(db))

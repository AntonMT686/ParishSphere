from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Scope = Literal["PARISH", "SAME_ORG_UNIT", "PARENT_ORG_UNIT"]


class AssigneeRule(BaseModel):
    type: Literal["ROLE", "POSITION", "USER"]
    role: str | None = Field(default=None, max_length=50)
    position: str | None = Field(default=None, max_length=30)
    scope: Scope = "PARISH"
    user_id: str | None = Field(default=None, max_length=26, description="User public id (type USER)")

    @model_validator(mode="after")
    def _check(self) -> AssigneeRule:
        if self.type == "ROLE" and not self.role:
            raise ValueError("A role rule needs a role")
        if self.type == "POSITION":
            if not self.position:
                raise ValueError("A position rule needs a position")
            if self.scope == "PARISH":
                raise ValueError("A position rule must use the record's organisation or its parent")
        if self.type == "USER" and not self.user_id:
            raise ValueError("A user rule needs a user")
        return self


class RuleOut(AssigneeRule):
    label: str


class StageIn(BaseModel):
    key: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    kind: Literal["REVIEW", "APPROVE"] = "REVIEW"
    quorum: Literal["ANY", "ALL"] | int = "ANY"
    optional: bool = False
    sla_hours: int | None = Field(default=None, ge=1, le=2160)
    allow_delegation: bool = True
    assignees: list[AssigneeRule] = Field(min_length=1, max_length=10)
    escalate_to: list[AssigneeRule] = Field(default_factory=list, max_length=10)

    @field_validator("quorum")
    @classmethod
    def _quorum(cls, v: str | int) -> str | int:
        if isinstance(v, int) and not 1 <= v <= 20:
            raise ValueError("Quorum must be between 1 and 20 approvals")
        return v


class StageOut(StageIn):
    assignees: list[RuleOut]  # type: ignore[assignment]
    escalate_to: list[RuleOut]  # type: ignore[assignment]


class Conditions(BaseModel):
    org_unit_types: list[str] | None = Field(default=None, max_length=20)
    parish_level: bool | None = Field(default=None, description="true: only parish-level records")
    categories: list[str] | None = Field(default=None, max_length=50)
    min_amount: float | None = Field(default=None, ge=0)
    max_amount: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _range(self) -> Conditions:
        if self.min_amount is not None and self.max_amount is not None and self.min_amount > self.max_amount:
            raise ValueError("The minimum amount is larger than the maximum")
        return self


class DefinitionIn(BaseModel):
    entity_type: str = Field(max_length=30)
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    priority: int = Field(default=0, ge=0, le=1000)
    conditions: Conditions = Field(default_factory=Conditions)
    stages: list[StageIn] = Field(min_length=1, max_length=10)


class DefinitionUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    priority: int = Field(default=0, ge=0, le=1000)
    conditions: Conditions = Field(default_factory=Conditions)
    stages: list[StageIn] = Field(min_length=1, max_length=10)


class DefinitionOut(BaseModel):
    id: str
    code: str
    version: int
    is_latest: bool
    is_active: bool
    entity_type: str
    entity_label: str
    name: str
    description: str | None
    priority: int
    conditions: Conditions
    stages: list[StageOut]
    is_system: bool
    running: int = Field(description="Approvals in progress that started with this code")
    created_at: datetime
    updated_at: datetime


class EntityTypeOut(BaseModel):
    code: str
    label: str
    has_amount: bool
    has_category: bool
    definitions: int


class WorkflowRef(BaseModel):
    id: str
    name: str


class TaskBrief(BaseModel):
    id: str
    assignee: WorkflowRef
    delegated_from: WorkflowRef | None
    status: str
    is_escalation: bool
    due_at: datetime | None
    acted_at: datetime | None
    acted_by: WorkflowRef | None
    comment: str | None


class InstanceSummary(BaseModel):
    id: str
    entity_type: str
    entity_label: str
    entity_id: str
    title: str
    link: str | None
    org_unit: WorkflowRef | None
    amount: float | None
    category: str | None
    status: str
    cycle: int
    stage_index: int
    stage_name: str | None
    stage_count: int
    pending_with: list[str]
    submitted_by: WorkflowRef
    submitted_at: datetime
    completed_at: datetime | None


class StageState(BaseModel):
    index: int
    name: str
    kind: str
    quorum: str
    optional: bool
    state: Literal["DONE", "CURRENT", "UPCOMING", "SKIPPED"]
    tasks: list[TaskBrief]


class ActionOut(BaseModel):
    id: int
    action: str
    actor: WorkflowRef | None
    on_behalf_of: WorkflowRef | None
    comment: str | None
    cycle: int
    stage_name: str | None
    prev_status: str | None
    new_status: str | None
    created_at: datetime


class InstanceDetail(InstanceSummary):
    definition: dict[str, str | int]
    stages: list[StageState]
    actions: list[ActionOut]
    my_task: str | None = Field(description="Your pending task on this record, if any")
    can_withdraw: bool
    can_resubmit: bool
    can_override: bool


class TaskOut(BaseModel):
    id: str
    status: str
    stage_index: int
    stage_name: str
    kind: str
    is_escalation: bool
    delegated_from: WorkflowRef | None
    due_at: datetime | None
    overdue: bool
    created_at: datetime
    acted_at: datetime | None
    comment: str | None
    instance: InstanceSummary


class TaskSummaryOut(BaseModel):
    pending: int
    overdue: int


class ActIn(BaseModel):
    action: Literal["APPROVE", "REJECT", "RETURN", "DELEGATE"]
    comment: str | None = Field(default=None, max_length=2000)
    delegate_user_id: str | None = Field(default=None, max_length=26)


class BulkApproveIn(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=50)
    comment: str | None = Field(default=None, max_length=2000)


class BulkResult(BaseModel):
    approved: list[str]
    failed: list[dict[str, str]]


class CommentIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class PreviewIn(BaseModel):
    entity_type: str = Field(max_length=30)
    org_unit_id: str | None = Field(default=None, max_length=26)
    amount: float | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=50)
    submitter_user_id: str | None = Field(default=None, max_length=26)
    stages: list[StageIn] | None = Field(default=None, description="Preview unsaved stages instead")


class PreviewAssignee(BaseModel):
    name: str
    delegated_from: str | None


class PreviewStage(BaseModel):
    index: int
    name: str
    quorum: str
    skipped: bool
    fallback: bool
    assignees: list[PreviewAssignee]


class PreviewOut(BaseModel):
    definition: dict[str, str | int] | None
    stages: list[PreviewStage]


class DelegationIn(BaseModel):
    delegate_user_id: str = Field(max_length=26)
    delegator_user_id: str | None = Field(default=None, max_length=26, description="Administrators only")
    valid_from: date | None = None
    valid_to: date | None = None
    entity_types: list[str] | None = None
    reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _dates(self) -> DelegationIn:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("The end date is before the start date")
        return self


class DelegationOut(BaseModel):
    id: str
    delegator: WorkflowRef
    delegate: WorkflowRef
    valid_from: date
    valid_to: date | None
    entity_types: list[str] | None
    reason: str | None
    active: bool
    ended_at: datetime | None

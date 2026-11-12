"""Configurable approval workflows: versioned definitions, instances, tasks, actions, delegations."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow


class WorkflowDefinition(StandardMixin, TenantBase):
    """One *version* of an approval process. Editing creates a new version (same ``code``); running
    instances keep a snapshot of the version they started with."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("code", "version"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Higher wins when several definitions match the record.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # {"org_unit_types": [...], "categories": [...], "min_amount": n, "max_amount": n, "parish_level": bool}
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # [{"key", "name", "kind": REVIEW|APPROVE, "quorum": ANY|ALL|<n>, "optional", "sla_hours",
    #   "allow_delegation", "assignees": [rule...], "escalate_to": [rule...]}]
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "version": self.version,
            "name": self.name,
            "entity_type": self.entity_type,
            "conditions": self.conditions,
            "stages": self.stages,
        }


class WorkflowInstance(IdMixin, PublicIdMixin, TenantBase):
    """One run of a definition for one record."""

    __tablename__ = "workflow_instances"

    definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id"), nullable=False, index=True
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    link: Mapped[str | None] = mapped_column(String(255))
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # IN_PROGRESS, REWORK, APPROVED, REJECTED, CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="IN_PROGRESS", index=True)
    cycle: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime())
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    tasks: Mapped[list[WorkflowTask]] = relationship(
        back_populates="instance", order_by="WorkflowTask.id", lazy="selectin"
    )
    actions: Mapped[list[WorkflowAction]] = relationship(order_by="WorkflowAction.id", lazy="selectin")

    @property
    def stages(self) -> list[dict[str, Any]]:
        return list(self.snapshot.get("stages", []))

    @property
    def active(self) -> bool:
        return self.status in ("IN_PROGRESS", "REWORK")


class WorkflowTask(IdMixin, PublicIdMixin, TenantBase):
    """A decision one user owes at one stage of one cycle."""

    __tablename__ = "workflow_tasks"

    instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instances.id"), nullable=False, index=True)
    cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_name: Mapped[str] = mapped_column(String(150), nullable=False)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # Set when the task reached the assignee through a delegation (the original assignee).
    delegated_from_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # PENDING, APPROVED, REJECTED, RETURNED, DELEGATED, CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    # Escalation tasks are extra: they may decide the stage but are never required for its quorum.
    is_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(), index=True)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime())
    acted_at: Mapped[datetime | None] = mapped_column(DateTime())
    acted_by: Mapped[int | None] = mapped_column(BigIntPK)  # differs from assignee on admin override
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="tasks")


class WorkflowAction(IdMixin, TenantBase):
    """Immutable history row."""

    __tablename__ = "workflow_actions"

    instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instances.id"), nullable=False, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_tasks.id"))
    cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_index: Mapped[int | None] = mapped_column(Integer)
    stage_name: Mapped[str | None] = mapped_column(String(150))
    # SUBMIT, APPROVE, REJECT, RETURN, DELEGATE, RESUBMIT, WITHDRAW, SKIP, FALLBACK, ESCALATE, COMPLETE
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # None = system
    on_behalf_of_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    prev_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class WorkflowDelegation(IdMixin, PublicIdMixin, TenantBase):
    """While active, new tasks for ``delegator`` go to ``delegate`` instead (e.g. during leave)."""

    __tablename__ = "workflow_delegations"

    delegator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    delegate_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    entity_types: Mapped[list[str] | None] = mapped_column(JSON)  # None = every workflow
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(BigIntPK)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime())
    ended_by: Mapped[int | None] = mapped_column(BigIntPK)

    def is_active_on(self, day: date) -> bool:
        return (
            self.ended_at is None
            and self.valid_from <= day
            and (self.valid_to is None or self.valid_to >= day)
        )

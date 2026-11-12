"""Workflowable entity types and the callbacks business modules register for them.

The engine never touches business tables itself: a module registers a :class:`WorkflowHandler` whose
callbacks move its record between statuses (e.g. Activity → IN_REVIEW / APPROVED / REWORK).
Callbacks run inside the engine's transaction, so a failing callback rolls the whole step back.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.modules.workflow.models import WorkflowInstance

Callback = Callable[[Session, "WorkflowInstance"], None]


@dataclass(frozen=True)
class EntityType:
    code: str
    label: str
    module: str  # permission module: viewers of the record may view its approval history
    has_amount: bool = False
    has_category: bool = False


ENTITY_TYPES: dict[str, EntityType] = {
    e.code: e
    for e in (
        EntityType("ACTIVITY", "Activity", "activity", has_category=True),
        EntityType("MEETING_MINUTES", "Meeting minutes", "meeting"),
        EntityType("FIN_TRANSACTION", "Financial transaction", "finance", has_amount=True, has_category=True),
        EntityType("FIN_PERIOD", "Monthly statement", "finance_period"),
        EntityType("NOTICE", "Notice", "notice", has_category=True),
    )
}


@dataclass(frozen=True)
class WorkflowHandler:
    on_submitted: Callback | None = None  # also called on resubmission
    on_approved: Callback | None = None
    on_rejected: Callback | None = None
    on_rework: Callback | None = None
    on_withdrawn: Callback | None = None


_HANDLERS: dict[str, WorkflowHandler] = {}


def register_handler(entity_type: str, handler: WorkflowHandler) -> None:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown workflow entity type {entity_type!r}")
    _HANDLERS[entity_type] = handler


def unregister_handler(entity_type: str) -> None:
    _HANDLERS.pop(entity_type, None)


def handler_for(entity_type: str) -> WorkflowHandler:
    return _HANDLERS.get(entity_type, WorkflowHandler())


def has_handler(entity_type: str) -> bool:
    return entity_type in _HANDLERS

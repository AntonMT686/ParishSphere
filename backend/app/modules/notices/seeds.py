"""An emergency-notice workflow: straight to the Parish Priest, escalating to the Secretary after 2 hours."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.workflow.models import WorkflowDefinition
from app.modules.workflow.seeds import role, stage
from app.tenancy.seed import register_seeder


@register_seeder("notices.workflows", order=65)
def seed_notice_workflows(session: Session, _: dict[str, Any]) -> None:
    if session.scalar(
        select(WorkflowDefinition.id).where(WorkflowDefinition.code == "NOTICE_EMERGENCY").limit(1)
    ):
        return
    session.add(
        WorkflowDefinition(
            code="NOTICE_EMERGENCY",
            version=1,
            is_latest=True,
            is_active=True,
            entity_type="NOTICE",
            name="Emergency notice approval",
            description="Parish Priest only; escalates to the Parish Secretary after 2 hours.",
            priority=10,
            conditions={"categories": ["EMERGENCY"]},
            is_system=True,
            stages=[
                stage(
                    "parish_priest",
                    "Parish Priest",
                    [role("PARISH_PRIEST")],
                    kind="APPROVE",
                    sla_hours=2,
                    escalate_to=[role("PARISH_SECRETARY")],
                )
            ],
        )
    )

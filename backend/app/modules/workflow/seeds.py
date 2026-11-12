"""Default approval workflows seeded into every parish (docs/05-workflow-engine.md §7).

Seeding is idempotent and never overwrites a parish's own versions: a definition ``code`` that already
exists is left alone.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.workflow.models import WorkflowDefinition
from app.tenancy.seed import register_seeder


def role(code: str) -> dict[str, Any]:
    return {"type": "ROLE", "role": code, "scope": "PARISH"}


def position(code: str, scope: str = "SAME_ORG_UNIT") -> dict[str, Any]:
    return {"type": "POSITION", "position": code, "scope": scope}


def stage(key: str, name: str, assignees: list[dict[str, Any]], *, kind: str = "REVIEW", quorum: Any = "ANY",
          optional: bool = False, sla_hours: int | None = 72,
          escalate_to: list[dict[str, Any]] | None = None) -> dict[str, Any]:  # fmt: skip
    return {
        "key": key,
        "name": name,
        "kind": kind,
        "quorum": quorum,
        "optional": optional,
        "sla_hours": sla_hours,
        "allow_delegation": True,
        "assignees": assignees,
        "escalate_to": escalate_to or [],
    }


ORG_PRESIDENT = stage(
    "org_president", "President of the organisation", [position("PRESIDENT")], optional=True
)
PARISH_SECRETARY = stage("parish_secretary", "Parish Secretary", [role("PARISH_SECRETARY")], optional=True)
PARISH_PRIEST = stage(
    "parish_priest", "Parish Priest", [role("PARISH_PRIEST")], kind="APPROVE", sla_hours=120
)
PARISH_TREASURER = stage("parish_treasurer", "Parish Treasurer", [role("PARISH_TREASURER")], optional=True,
                         escalate_to=[role("PARISH_PRIEST")])  # fmt: skip

DEFAULTS: tuple[dict[str, Any], ...] = (
    {
        "code": "ACTIVITY_DEFAULT",
        "entity_type": "ACTIVITY",
        "name": "Activity approval",
        "description": "President of the organisation → Parish Secretary → Parish Priest.",
        "stages": [ORG_PRESIDENT, PARISH_SECRETARY, PARISH_PRIEST],
    },
    {
        "code": "MINUTES_DEFAULT",
        "entity_type": "MEETING_MINUTES",
        "name": "Meeting minutes approval",
        "description": "President of the organisation → Parish Priest.",
        "stages": [ORG_PRESIDENT, PARISH_PRIEST],
    },
    {
        "code": "FIN_TXN_DEFAULT",
        "entity_type": "FIN_TRANSACTION",
        "name": "Financial transaction approval",
        "description": "Parish Treasurer → Parish Priest.",
        "stages": [PARISH_TREASURER, PARISH_PRIEST],
    },
    {
        "code": "FIN_TXN_LARGE",
        "entity_type": "FIN_TRANSACTION",
        "name": "Large transaction approval (₹50,000 and above)",
        "description": "Parish Treasurer → Parish President and Parish Secretary (both) → Parish Priest.",
        "priority": 10,
        "conditions": {"min_amount": 50000},
        "stages": [
            PARISH_TREASURER,
            stage(
                "council_officers",
                "Parish President & Parish Secretary",
                [role("PARISH_PRESIDENT"), role("PARISH_SECRETARY")],
                quorum="ALL",
            ),  # fmt: skip
            PARISH_PRIEST,
        ],
    },
    {
        "code": "FIN_PERIOD_DEFAULT",
        "entity_type": "FIN_PERIOD",
        "name": "Monthly statement approval",
        "description": "Parish Priest approves the closed month before the statement is generated.",
        "stages": [PARISH_PRIEST],
    },
    {
        "code": "NOTICE_DEFAULT",
        "entity_type": "NOTICE",
        "name": "Notice approval",
        "description": "Parish Secretary or Parish President → Parish Priest.",
        "stages": [
            stage(
                "council_review",
                "Parish Secretary or President",
                [role("PARISH_SECRETARY"), role("PARISH_PRESIDENT")],
                optional=True,
                sla_hours=48,
            ),  # fmt: skip
            PARISH_PRIEST,
        ],
    },
)


@register_seeder("workflow.definitions", order=60)
def seed_definitions(session: Session, _: dict[str, Any]) -> None:
    have = set(session.scalars(select(WorkflowDefinition.code)))
    for d in DEFAULTS:
        if d["code"] in have:
            continue
        session.add(
            WorkflowDefinition(
                code=d["code"],
                version=1,
                is_latest=True,
                is_active=True,
                entity_type=d["entity_type"],
                name=d["name"],
                description=d["description"],
                priority=d.get("priority", 0),
                conditions=d.get("conditions", {}),
                stages=d["stages"],
                is_system=True,
            )
        )

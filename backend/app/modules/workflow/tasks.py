"""Periodic workflow jobs: SLA reminders and escalation, run for every active parish."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.master import master_session
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.master.models import Parish, ParishStatus
from app.modules.workflow.service import process_overdue
from app.tenancy.resolver import descriptor_from_parish
from app.worker import celery_app

log = structlog.get_logger("app.workflow")


def active_tenants() -> list[TenantDescriptor]:
    with master_session() as s:
        rows = s.scalars(
            select(Parish)
            .options(joinedload(Parish.database), joinedload(Parish.diocese))
            .where(Parish.status.in_([ParishStatus.ACTIVE, ParishStatus.TRIAL]), Parish.is_deleted.is_(False))
        ).unique()
        return [descriptor_from_parish(p) for p in rows if p.database is not None]


def run_sla_sweep(only: list[str] | None = None) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    for t in active_tenants():
        if only and t.code not in {c.upper() for c in only}:
            continue
        try:
            with tenant_session_scope(t) as s:
                results[t.code] = process_overdue(s, t)
        except Exception:  # one broken parish must not stop the others
            log.exception("workflow_sla_failed", parish=t.code)
    return results


@celery_app.task(name="app.tasks.workflow.sla_sweep")
def sla_sweep() -> dict[str, dict[str, int]]:
    return run_sla_sweep()

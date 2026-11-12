"""Hourly reminders: upcoming meetings and due / overdue action items, for every active parish."""

from __future__ import annotations

import structlog

from app.db.tenant import tenant_session_scope
from app.modules.activities.service import run_reminders
from app.modules.workflow.tasks import active_tenants
from app.worker import celery_app

log = structlog.get_logger("app.reminders")


def run_all_reminders(only: list[str] | None = None) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    for t in active_tenants():
        if only and t.code not in {c.upper() for c in only}:
            continue
        try:
            with tenant_session_scope(t) as s:
                results[t.code] = run_reminders(s, t)
        except Exception:
            log.exception("reminders_failed", parish=t.code)
    return results


@celery_app.task(name="app.tasks.maintenance.reminders")
def reminders() -> dict[str, dict[str, int]]:
    return run_all_reminders()

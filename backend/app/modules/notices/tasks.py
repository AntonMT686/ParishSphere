"""Publish scheduled notices when their time comes and notify their audience."""

from __future__ import annotations

import structlog

from app.db.tenant import tenant_session_scope
from app.modules.notices.service import publish_due
from app.modules.workflow.tasks import active_tenants
from app.worker import celery_app

log = structlog.get_logger("app.notices")


def run_publish_due(only: list[str] | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in active_tenants():
        if only and t.code not in {c.upper() for c in only}:
            continue
        try:
            with tenant_session_scope(t) as s:
                out[t.code] = publish_due(s, t)
        except Exception:
            log.exception("notice_publish_failed", parish=t.code)
    return out


@celery_app.task(name="app.tasks.maintenance.publish_notices")
def publish_notices() -> dict[str, int]:
    return run_publish_due()

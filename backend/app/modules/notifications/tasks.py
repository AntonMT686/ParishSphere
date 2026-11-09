"""Celery tasks for outbound notification delivery."""

from __future__ import annotations

from app.modules.notifications.service import deliver
from app.worker import celery_app

MAX_RETRIES = 5


@celery_app.task(
    name="app.tasks.notifications.send_outbound",
    bind=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
)
def send_outbound(self, tenant_code: str, message_id: int) -> str:  # type: ignore[no-untyped-def]
    try:
        return deliver(tenant_code, message_id, raise_errors=True)
    except Exception as exc:
        # 30s, 60s, 120s, 240s, 480s
        raise self.retry(exc=exc, countdown=30 * 2**self.request.retries) from exc

"""Celery application. Tasks always receive the tenant code explicitly (no request context)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()
_broker = _settings.redis_url or "memory://"

celery_app = Celery("parishsphere", broker=_broker, backend=_settings.redis_url or None)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "app.tasks.notifications.*": {"queue": "notifications"},
        "app.tasks.documents.*": {"queue": "documents"},
        "app.tasks.workflow.*": {"queue": "workflow"},
        "app.tasks.maintenance.*": {"queue": "maintenance"},
    },
)


@celery_app.task(name="app.tasks.maintenance.ping")
def ping() -> str:
    return "pong"

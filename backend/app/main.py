"""FastAPI application factory."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.db.registry
from app.common.files_router import router as files_router
from app.core.config import get_settings
from app.core.context import set_tenant_code, set_trace_id, set_user_id
from app.core.errors import register_exception_handlers
from app.core.ids import new_public_id
from app.core.logging import configure_logging
from app.db.master import get_master_engine
from app.master.router import router as platform_router
from app.modules.activities.router import actions_router, activities_router, calendar_router, meetings_router
from app.modules.audit.router import router as audit_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.finance.router import router as finance_router
from app.modules.identity.router import router as auth_router
from app.modules.notices.router import public_router as public_notices_router
from app.modules.notices.router import router as notices_router
from app.modules.notifications.router import router as notifications_router
from app.modules.org_units.router import types_router as org_types_router
from app.modules.org_units.router import units_router as org_units_router
from app.modules.parish.router import parish_router, priests_router
from app.modules.people.router import families as families_router
from app.modules.people.router import members as members_router
from app.modules.people.router import memberships as memberships_router
from app.modules.rbac.router import router as roles_router
from app.modules.users.router import router as users_router
from app.modules.workflow.router import router as workflow_router
from app.tenancy.router import router as tenant_router

log = structlog.get_logger("app.request")

API_PREFIX = "/api/v1"


def _health_router() -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    def ready(response: Response) -> dict[str, object]:
        checks: dict[str, str] = {}
        try:
            with get_master_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["master_db"] = "ok"
        except Exception:
            checks["master_db"] = "error"
        settings = get_settings()
        if settings.redis_url:
            try:
                import redis

                redis.Redis.from_url(settings.redis_url, socket_timeout=0.5).ping()
                checks["redis"] = "ok"
            except Exception:
                checks["redis"] = "error"
        ok = all(v == "ok" for v in checks.values())
        response.status_code = 200 if ok else 503
        return {"status": "ok" if ok else "degraded", "checks": checks}

    return router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    docs = settings.expose_docs
    app = FastAPI(
        title="ParishSphere API",
        version="0.1.0",
        description="One Digital Platform. Every Parish. Every Family. Every Ministry.",
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
    )
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Parish-Code", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = request.headers.get("x-request-id") or new_public_id()
        set_trace_id(trace_id)
        set_tenant_code(None)
        set_user_id(None)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response

    app.include_router(_health_router(), prefix=API_PREFIX)
    app.include_router(platform_router, prefix=API_PREFIX)
    app.include_router(tenant_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(users_router, prefix=API_PREFIX)
    app.include_router(roles_router, prefix=API_PREFIX)
    app.include_router(notifications_router, prefix=API_PREFIX)
    app.include_router(audit_router, prefix=API_PREFIX)
    app.include_router(org_types_router, prefix=API_PREFIX)
    app.include_router(org_units_router, prefix=API_PREFIX)
    app.include_router(memberships_router, prefix=API_PREFIX)
    app.include_router(families_router, prefix=API_PREFIX)
    app.include_router(members_router, prefix=API_PREFIX)
    app.include_router(parish_router, prefix=API_PREFIX)
    app.include_router(priests_router, prefix=API_PREFIX)
    app.include_router(workflow_router, prefix=API_PREFIX)
    app.include_router(finance_router, prefix=API_PREFIX)
    app.include_router(notices_router, prefix=API_PREFIX)
    app.include_router(public_notices_router, prefix=API_PREFIX)
    app.include_router(dashboard_router, prefix=API_PREFIX)
    for r in (activities_router, meetings_router, actions_router, calendar_router):
        app.include_router(r, prefix=API_PREFIX)
    app.include_router(files_router, prefix=API_PREFIX)
    return app


app = create_app()

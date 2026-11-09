"""FastAPI application factory."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.context import set_tenant_code, set_trace_id, set_user_id
from app.core.errors import register_exception_handlers
from app.core.ids import new_public_id
from app.core.logging import configure_logging
from app.db.master import get_master_engine
from app.master.router import router as platform_router
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
    return app


app = create_app()

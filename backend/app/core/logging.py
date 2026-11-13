"""Structured logging (structlog) enriched with trace id, tenant and user."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.context import get_tenant_code, get_trace_id, get_user_id


def _add_context(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if (trace_id := get_trace_id()) is not None:
        event_dict.setdefault("trace_id", trace_id)
    if (tenant := get_tenant_code()) is not None:
        event_dict.setdefault("tenant", tenant)
    if (user := get_user_id()) is not None:
        event_dict.setdefault("user", user)
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level.upper(), stream=sys.stdout, format="%(levelname)s %(name)s %(message)s")
    # PDF rendering libraries log every glyph table at DEBUG/INFO; keep them out of application logs.
    # WeasyPrint briefly raises fontTools to DEBUG while subsetting fonts (and reports problems itself),
    # so fontTools records must not reach our handlers at all.
    for noisy in ("fontTools", "weasyprint", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("fontTools").propagate = False

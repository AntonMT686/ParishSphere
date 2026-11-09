"""Request-scoped context variables (trace id, tenant code, user id) used by logging."""

from __future__ import annotations

from contextvars import ContextVar

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_tenant_code: ContextVar[str | None] = ContextVar("tenant_code", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


def get_trace_id() -> str | None:
    return _trace_id.get()


def set_trace_id(value: str | None) -> object:
    return _trace_id.set(value)


def get_tenant_code() -> str | None:
    return _tenant_code.get()


def set_tenant_code(value: str | None) -> object:
    return _tenant_code.set(value)


def get_user_id() -> str | None:
    return _user_id.get()


def set_user_id(value: str | None) -> object:
    return _user_id.set(value)

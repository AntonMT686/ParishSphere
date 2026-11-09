"""Audit trail writer for parish databases (append-only ``audit_logs``).

Call :func:`record_audit` inside the same session/transaction as the business change so the audit
row commits or rolls back with it. Sensitive keys are masked before storage.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.modules.core.models import AuditLog

SENSITIVE_KEYS = {"password", "password_hash", "token", "token_hash", "refresh_token", "secret", "pin"}


def mask(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    return {
        k: ("***" if any(s in k.lower() for s in SENSITIVE_KEYS) else _jsonable(v)) for k, v in values.items()
    }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    return str(value)


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host if request.client else None


def record_audit(
    session: Session,
    *,
    action: str,
    module: str,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    request: Request | None = None,
    old: dict[str, Any] | None = None,
    new: dict[str, Any] | None = None,
    remarks: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        module=module,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255] if request is not None else None,
        old_values=mask(old),
        new_values=mask(new),
        remarks=remarks,
    )
    session.add(entry)
    return entry

"""Audit trail writer for parish databases (append-only ``audit_logs``).

Call :func:`record_audit` inside the same session/transaction as the business change so the audit
row commits or rolls back with it. Sensitive keys are masked before storage.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session

from app.modules.core.models import AuditLog


class AuditTamperError(RuntimeError):
    """Raised when code tries to change or delete an audit row."""


@event.listens_for(Session, "before_flush")
def _audit_rows_are_append_only(session: Session, _ctx: object, _instances: object) -> None:
    for obj in (*session.dirty, *session.deleted):
        if isinstance(obj, AuditLog) and (obj in session.deleted or session.is_modified(obj)):
            raise AuditTamperError("Audit log entries cannot be changed or deleted")


@event.listens_for(Session, "do_orm_execute")
def _no_bulk_audit_changes(state: ORMExecuteState) -> None:
    if (state.is_update or state.is_delete) and any(m.class_ is AuditLog for m in (state.all_mappers or ())):
        raise AuditTamperError("Audit log entries cannot be changed or deleted")


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


def changes(obj: Any, *, exclude: set[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pending column changes of an ORM object as ``(old, new)`` dicts — call before flush/commit.

    Use with :func:`record_audit`::

        old, new = changes(family)
        record_audit(db, action="UPDATE", module="families", old=old, new=new, ...)
    """
    from sqlalchemy import inspect

    skip = {"updated_at", "updated_by", "created_at", "created_by"} | (exclude or set())
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    state = inspect(obj)
    for attr in state.mapper.column_attrs:
        if attr.key in skip:
            continue
        hist = state.attrs[attr.key].history
        if hist.has_changes():
            old[attr.key] = hist.deleted[0] if hist.deleted else None
            new[attr.key] = hist.added[0] if hist.added else None
    return old, new

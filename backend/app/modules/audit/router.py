"""Audit log viewer (``/api/v1/audit-logs``). Read-only: the API offers no way to alter audit rows."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.common.audit import record_audit
from app.common.exports import Column, ExportFormat, export_table
from app.common.pagination import Page, PageQuery, apply_sort
from app.modules.core.models import AuditLog
from app.modules.identity.deps import Auth
from app.modules.identity.models import User
from app.modules.rbac.deps import require_perm
from app.modules.rbac.service import PermissionScope
from app.tenancy.deps import TenantSession

router = APIRouter(prefix="/audit-logs", tags=["audit"])

CanView = Annotated[PermissionScope, Depends(require_perm("audit.view", parish_wide=True))]
CanExport = Annotated[PermissionScope, Depends(require_perm("audit.export", parish_wide=True))]


class AuditLogOut(BaseModel):
    id: int
    occurred_at: datetime
    user_id: str | None
    username: str | None
    action: str
    module: str
    entity_type: str | None
    entity_id: str | None
    ip: str | None
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    remarks: str | None


class AuditFilters(BaseModel):
    q: str | None = None
    user: str | None = None
    action: str | None = None
    module: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None


def audit_filters(
    q: Annotated[str | None, Query(max_length=100, description="Search remarks / entity id")] = None,
    user: Annotated[str | None, Query(description="User public id")] = None,
    action: Annotated[str | None, Query(max_length=50)] = None,
    module: Annotated[str | None, Query(max_length=50)] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AuditFilters:
    return AuditFilters(
        q=q,
        user=user,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
    )


Filters = Annotated[AuditFilters, Depends(audit_filters)]


def _query(db: Session, f: AuditFilters) -> Select[Any]:
    stmt = select(AuditLog, User).outerjoin(User, User.id == AuditLog.user_id)
    if f.user:
        stmt = stmt.where(User.public_id == f.user)
    if f.action:
        stmt = stmt.where(AuditLog.action == f.action.upper())
    if f.module:
        stmt = stmt.where(AuditLog.module == f.module.lower())
    if f.entity_type:
        stmt = stmt.where(AuditLog.entity_type == f.entity_type)
    if f.entity_id:
        stmt = stmt.where(AuditLog.entity_id == f.entity_id)
    if f.date_from:
        stmt = stmt.where(AuditLog.occurred_at >= datetime.combine(f.date_from, time.min))
    if f.date_to:
        stmt = stmt.where(AuditLog.occurred_at < datetime.combine(f.date_to + timedelta(days=1), time.min))
    if f.q:
        like = f"%{f.q}%"
        stmt = stmt.where(or_(AuditLog.remarks.ilike(like), AuditLog.entity_id.ilike(like)))
    return stmt


def _out(row: Any) -> AuditLogOut:
    log, user = row
    return AuditLogOut(
        id=log.id,
        occurred_at=log.occurred_at,
        user_id=user.public_id if user else None,
        username=user.username if user else None,
        action=log.action,
        module=log.module,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        ip=log.ip,
        old_values=log.old_values,
        new_values=log.new_values,
        remarks=log.remarks,
    )


SORT = {"occurred_at": AuditLog.occurred_at, "action": AuditLog.action, "module": AuditLog.module}


@router.get("", response_model=Page[AuditLogOut])
def list_audit_logs(_: CanView, db: TenantSession, params: PageQuery, f: Filters) -> Page[AuditLogOut]:
    stmt = apply_sort(_query(db, f), params.sort, SORT, [AuditLog.occurred_at.desc(), AuditLog.id.desc()])
    total_stmt = stmt.with_only_columns(AuditLog.id)
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(total_stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.limit(params.size).offset(params.offset)).all()
    return Page[AuditLogOut](
        items=[_out(r) for r in rows],
        page=params.page,
        size=params.size,
        total=total,
        pages=(total + params.size - 1) // params.size,
    )


@router.get("/export")
def export_audit_logs(
    request: Request,
    auth: Auth,
    _: CanExport,
    db: TenantSession,
    f: Filters,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    stmt = _query(db, f).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    rows = [_out(r).model_dump() for r in db.execute(stmt).all()]
    record_audit(
        db,
        action="EXPORT",
        module="audit",
        user_id=auth.user.id,
        request=request,
        remarks=f"{len(rows)} audit rows as {format.value}",
        new=f.model_dump(mode="json"),
    )
    columns = [
        Column("occurred_at", "When (UTC)", 18),
        Column("username", "User", 16),
        Column("action", "Action", 18),
        Column("module", "Module", 12),
        Column("entity_type", "Entity", 12),
        Column("entity_id", "Record", 28),
        Column("ip", "IP", 15),
        Column("remarks", "Remarks", 40),
    ]
    if format is not ExportFormat.PDF:
        columns += [
            Column("old_values", "Old values", 40, formatter=_json),
            Column("new_values", "New values", 40, formatter=_json),
        ]
    return export_table(
        rows,
        columns,
        format,
        title="Audit log",
        filename="audit-log",
        parish_name=auth.tenant.name,
        generated_by=auth.user.full_name,
    )


def _json(value: Any) -> str:
    import json

    return "" if value is None else json.dumps(value, ensure_ascii=False, default=str)

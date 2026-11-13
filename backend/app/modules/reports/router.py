"""Reports API: catalog, on-screen preview and CSV / Excel / PDF export."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.common.audit import record_audit
from app.common.exports import ExportFormat, _plain, export_table
from app.core.errors import NotFound, PermissionDenied
from app.modules.identity.deps import Auth, AuthContext
from app.modules.org_units.models import OrgUnitType
from app.tenancy.deps import TenantSession

from . import activities, finance, management, parish  # noqa: F401  (registers the reports)
from .base import REPORTS, Ctx, ReportDef, ReportParams, Result

router = APIRouter(prefix="/reports", tags=["reports"])
PREVIEW_ROWS = 500


class ParamOption(BaseModel):
    value: str
    label: str


class ParamOut(BaseModel):
    name: str
    options: list[ParamOption] = []
    default: str | None = None


class ReportInfo(BaseModel):
    code: str
    group: str
    title: str
    description: str
    params: list[ParamOut]
    can_export: bool


class ColumnOut(BaseModel):
    key: str
    header: str
    kind: str


class ReportOut(BaseModel):
    code: str
    title: str
    subtitle: str | None
    note: str | None
    columns: list[ColumnOut]
    rows: list[dict[str, Any]]
    totals: dict[str, Any] | None
    total_rows: int
    truncated: bool


def _allowed(auth: AuthContext, r: ReportDef, perm: str = "report.view") -> bool:
    if not auth.permissions.scope(perm).granted:
        return False
    s = auth.permissions.scope(r.permission)
    return s.parish_wide if r.parish_wide else s.granted


def _get(auth: AuthContext, code: str, perm: str) -> ReportDef:
    r = REPORTS.get(code)
    if r is None or not _allowed(auth, r, "report.view"):
        raise NotFound("Report not found")
    if not _allowed(auth, r, perm):
        raise PermissionDenied(details=[{"field": "permission", "message": perm}])
    return r


def params_dep(
    date_from: date | None = None,
    date_to: date | None = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    fy: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    org_unit: Annotated[str | None, Query(max_length=26)] = None,
    org_type: Annotated[str | None, Query(max_length=30)] = None,
    status: Annotated[str | None, Query(max_length=30)] = None,
    sacrament: Annotated[str | None, Query(max_length=20)] = None,
    gender: Annotated[str | None, Query(max_length=1)] = None,
) -> ReportParams:
    return ReportParams(
        date_from=date_from, date_to=date_to, month=month, fy=fy, org_unit=org_unit,
        org_type=org_type, status=status, sacrament=sacrament, gender=gender,
    )  # fmt: skip


Params = Annotated[ReportParams, Depends(params_dep)]


def _run(db: Any, auth: AuthContext, r: ReportDef, p: ReportParams) -> Result:
    return r.run(Ctx(db=db, auth=auth, p=p, scope=auth.permissions.scope(r.permission)))


def _cell(v: Any) -> Any:
    if isinstance(v, int | float) and not isinstance(v, bool):
        return v
    return _plain(v) if v is not None else None


@router.get("", response_model=list[ReportInfo])
def catalog(auth: Auth, db: TenantSession) -> list[ReportInfo]:
    types = [
        (t.code, t.name_plural)
        for t in db.scalars(
            select(OrgUnitType).where(OrgUnitType.is_deleted.is_(False)).order_by(OrgUnitType.sort_order)
        )
    ]
    out = []
    for r in REPORTS.values():
        if not _allowed(auth, r):
            continue
        params = []
        for p in r.params:
            opts = p.options if p.name != "org_type" else tuple(types)
            params.append(
                ParamOut(
                    name=p.name,
                    default=p.default,
                    options=[ParamOption(value=v, label=lbl) for v, lbl in opts],
                )
            )
        out.append(
            ReportInfo(
                code=r.code,
                group=r.group,
                title=r.title,
                description=r.description,
                params=params,
                can_export=_allowed(auth, r, "report.export"),
            )  # fmt: skip
        )
    return out


@router.get("/{code}", response_model=ReportOut)
def preview(code: str, auth: Auth, db: TenantSession, p: Params) -> ReportOut:
    r = _get(auth, code, "report.view")
    res = _run(db, auth, r, p)
    return ReportOut(
        code=r.code,
        title=r.title,
        subtitle=res.subtitle,
        note=res.note,
        columns=[ColumnOut(key=c.key, header=c.header, kind=c.kind) for c in res.columns],
        rows=[{c.key: _cell(row.get(c.key)) for c in res.columns} for row in res.rows[:PREVIEW_ROWS]],
        totals={k: _cell(v) for k, v in res.totals.items()} if res.totals else None,
        total_rows=len(res.rows),
        truncated=len(res.rows) > PREVIEW_ROWS,
    )


@router.get("/{code}/export")
def export(
    code: str,
    request: Request,
    auth: Auth,
    db: TenantSession,
    p: Params,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    r = _get(auth, code, "report.export")
    res = _run(db, auth, r, p)
    rows = list(res.rows)
    if res.totals:
        rows.append(res.totals)
    record_audit(
        db,
        action="REPORT_EXPORTED",
        module="reports",
        user_id=auth.user.id,
        request=request,
        entity_type="report",
        entity_id=r.code,
        new={
            "format": format.value,
            "rows": len(res.rows),
            **p.model_dump(exclude_none=True, mode="json"),
        },
    )
    return export_table(
        rows,
        [c.export() for c in res.columns],
        format,
        title=r.title,
        filename=r.code.replace("_", "-"),
        parish_name=auth.tenant.name,
        subtitle=res.subtitle,
        generated_by=auth.user.full_name,
    )

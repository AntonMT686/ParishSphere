"""Report framework: a report declares its parameters and the permission behind its data, and returns
columns + rows. The same result is previewed on screen and exported to CSV, Excel or PDF."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exports import Column
from app.core.errors import NotFound, ValidationFailed
from app.modules.identity.deps import AuthContext
from app.modules.org_units.models import OrgUnit
from app.modules.parish.models import ParishProfile
from app.modules.rbac.service import PermissionScope

Kind = Literal["text", "number", "money", "date", "status"]
Group = Literal["PARISH", "ACTIVITY", "FINANCE", "MANAGEMENT"]


@dataclass(frozen=True)
class Col:
    key: str
    header: str
    kind: Kind = "text"

    def export(self) -> Column:
        return Column(self.key, self.header, numeric=self.kind in ("number", "money"))


@dataclass(frozen=True)
class Param:
    name: str  # date_range | month | fy | org_unit | org_type | status | sacrament | gender
    options: tuple[tuple[str, str], ...] = ()  # for selects: (value, label)
    default: str | None = None


class ReportParams(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    month: str | None = None  # YYYY-MM
    fy: int | None = None  # start year of the financial year
    org_unit: str | None = None
    org_type: str | None = None
    status: str | None = None
    sacrament: str | None = None
    gender: str | None = None


@dataclass
class Result:
    columns: list[Col]
    rows: list[dict[str, Any]]
    subtitle: str | None = None
    totals: dict[str, Any] | None = None  # shown as the last row (preview and exports)
    note: str | None = None


@dataclass
class Ctx:
    db: Session
    auth: AuthContext
    p: ReportParams
    scope: PermissionScope

    # ------------------------------------------------------------------ parameter helpers
    def today(self) -> date:
        return date.today()

    def fy_start(self, on: date | None = None) -> date:
        prof = self.db.get(ParishProfile, 1)
        m = prof.fy_start_month if prof else 4
        d = on or self.today()
        return date(d.year if d.month >= m else d.year - 1, m, 1)

    def fy_label(self, start: date) -> str:
        return f"FY {start.year}" if start.month == 1 else f"FY {start.year}–{str(start.year + 1)[2:]}"

    def range(self, default: Literal["fy", "month", "year", "all"] = "fy") -> tuple[date | None, date | None]:
        """The requested date range, or a sensible default (financial year to date)."""
        lo, hi = self.p.date_from, self.p.date_to
        if lo is None and hi is None:
            t = self.today()
            if default == "fy":
                lo, hi = self.fy_start(), t
            elif default == "month":
                lo, hi = t.replace(day=1), t
            elif default == "year":
                lo, hi = date(t.year - 1, t.month, 1), t
        if lo and hi and lo > hi:
            raise ValidationFailed("The start date is after the end date", code="BAD_RANGE")
        return lo, hi

    def range_label(self, lo: date | None, hi: date | None) -> str:
        if lo and hi:
            return f"{lo:%d %b %Y} – {hi:%d %b %Y}"
        if lo:
            return f"From {lo:%d %b %Y}"
        if hi:
            return f"Up to {hi:%d %b %Y}"
        return "All dates"

    def unit(self) -> OrgUnit | None:
        if not self.p.org_unit:
            return None
        u = self.db.scalar(
            select(OrgUnit).where(OrgUnit.public_id == self.p.org_unit, OrgUnit.is_deleted.is_(False))
        )
        if u is None:
            raise NotFound("Organisation not found")
        return u


@dataclass(frozen=True)
class ReportDef:
    code: str
    group: Group
    title: str
    description: str
    permission: str  # data permission, checked (with its scope) on top of report.view / report.export
    run: Callable[[Ctx], Result]
    params: tuple[Param, ...] = field(default_factory=tuple)
    parish_wide: bool = False  # the data permission must be parish-wide


REPORTS: dict[str, ReportDef] = {}


def report(
    code: str,
    group: Group,
    title: str,
    description: str,
    permission: str,
    params: tuple[Param, ...] = (),
    parish_wide: bool = False,
) -> Callable[[Callable[[Ctx], Result]], Callable[[Ctx], Result]]:
    def deco(fn: Callable[[Ctx], Result]) -> Callable[[Ctx], Result]:
        REPORTS[code] = ReportDef(code, group, title, description, permission, fn, params, parish_wide)
        return fn

    return deco


def money(v: Any) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"))


DATE_RANGE = Param("date_range")
ORG_UNIT = Param("org_unit")

"""Financial reports: monthly I&E, annual statement, donations, expense categories, organisation-wise,
pending approvals. Approved entries only (except the pending report); scoped like the ledger."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select

from app.core.errors import ValidationFailed
from app.modules.finance.models import FinAccount, FinCategory, FinTransaction
from app.modules.org_units.models import OrgUnit
from app.modules.people.models import Family

from .base import DATE_RANGE, ORG_UNIT, Col, Ctx, Param, Result, money, report

ZERO = Decimal("0.00")


def _approved(ctx: Ctx, lo: date | None, hi: date | None) -> Select[Any]:
    stmt = select(FinTransaction).where(
        FinTransaction.is_deleted.is_(False),
        FinTransaction.status == "APPROVED",
        ctx.scope.filter(FinTransaction.org_unit_id),
    )
    if lo:
        stmt = stmt.where(FinTransaction.txn_date >= lo)
    if hi:
        stmt = stmt.where(FinTransaction.txn_date <= hi)
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(FinTransaction.org_unit_id == u.id)
    return stmt


def _month(ctx: Ctx) -> tuple[date, date]:
    key = ctx.p.month
    t = ctx.today()
    if not key:
        y, m = t.year, t.month
    else:
        try:
            y, m = int(key[:4]), int(key[5:7])
            date(y, m, 1)
        except ValueError as e:
            raise ValidationFailed("Month must look like 2026-11", code="BAD_MONTH") from e
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start, min(date.fromordinal(end.toordinal() - 1), max(t, start))


def _cats(ctx: Ctx) -> dict[int, FinCategory]:
    return {c.id: c for c in ctx.db.scalars(select(FinCategory))}


@report(
    "income_expenditure", "FINANCE", "Monthly income and expenditure",
    "Income and expenditure by category for one month, with the surplus or deficit.",
    "finance.view", (Param("month"), ORG_UNIT),
)  # fmt: skip
def income_expenditure(ctx: Ctx) -> Result:
    lo, hi = _month(ctx)
    cats = _cats(ctx)
    sums: dict[tuple[str, int | None], Decimal] = defaultdict(lambda: ZERO)
    count: dict[tuple[str, int | None], int] = defaultdict(int)
    for t in ctx.db.scalars(_approved(ctx, lo, hi).where(FinTransaction.kind.in_(("INCOME", "EXPENSE")))):
        sums[(t.kind, t.category_id)] += t.amount
        count[(t.kind, t.category_id)] += 1
    rows: list[dict[str, Any]] = []
    totals = {"INCOME": ZERO, "EXPENSE": ZERO}
    for kind, label in (("INCOME", "Income"), ("EXPENSE", "Expenditure")):
        keys = sorted((k for k in sums if k[0] == kind), key=lambda k: -sums[k])
        for k in keys:
            c = cats.get(k[1] or 0)
            rows.append(
                {
                    "kind": label,
                    "category": c.name if c else "—",
                    "entries": count[k],
                    "amount": money(sums[k]),
                }
            )
            totals[kind] += sums[k]
        rows.append(
            {
                "kind": label,
                "category": f"Total {label.lower()}",
                "entries": None,
                "amount": money(totals[kind]),
            }
        )
    net = totals["INCOME"] - totals["EXPENSE"]
    return Result(
        [
            Col("kind", "Type"),
            Col("category", "Category"),
            Col("entries", "Entries", "number"),
            Col("amount", "Amount ₹", "money"),
        ],
        rows,
        subtitle=f"{lo:%B %Y}",
        totals={"category": "Surplus" if net >= 0 else "Deficit", "amount": money(net)},
    )


@report(
    "annual_statement", "FINANCE", "Annual financial statement",
    "Month-by-month income, expenditure and surplus for a financial year.",
    "finance.view", (Param("fy"), ORG_UNIT),
)  # fmt: skip
def annual_statement(ctx: Ctx) -> Result:
    start = ctx.fy_start()
    if ctx.p.fy:
        start = date(ctx.p.fy, start.month, 1)
    end = date(start.year + 1, start.month, 1)
    hi = min(date.fromordinal(end.toordinal() - 1), ctx.today())
    per: dict[str, dict[str, Decimal]] = {}
    d = start
    while d < end and d <= ctx.today():
        per[f"{d:%Y-%m}"] = {"INCOME": ZERO, "EXPENSE": ZERO}
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    for t in ctx.db.scalars(_approved(ctx, start, hi).where(FinTransaction.kind.in_(("INCOME", "EXPENSE")))):
        per[f"{t.txn_date:%Y-%m}"][t.kind] += t.amount
    rows = []
    running = ZERO
    for k, v in per.items():
        net = v["INCOME"] - v["EXPENSE"]
        running += net
        rows.append(
            {
                "month": date(int(k[:4]), int(k[5:]), 1).strftime("%B %Y"),
                "income": money(v["INCOME"]),
                "expense": money(v["EXPENSE"]),
                "net": money(net),
                "cumulative": money(running),
            }
        )
    inc = sum((r["income"] for r in rows), ZERO)
    exp = sum((r["expense"] for r in rows), ZERO)
    return Result(
        [
            Col("month", "Month"),
            Col("income", "Income ₹", "money"),
            Col("expense", "Expenditure ₹", "money"),
            Col("net", "Surplus / deficit ₹", "money"),
            Col("cumulative", "Year to date ₹", "money"),
        ],
        rows,
        subtitle=ctx.fy_label(start),
        totals={"month": "Total", "income": money(inc), "expense": money(exp), "net": money(inc - exp)},
    )


@report(
    "donation_report", "FINANCE", "Donation report",
    "Every approved donation with donor, family, mode and reference.",
    "finance.view", (DATE_RANGE, ORG_UNIT),
)  # fmt: skip
def donation_report(ctx: Ctx) -> Result:
    lo, hi = ctx.range()
    stmt = (
        _approved(ctx, lo, hi)
        .join(FinCategory, FinCategory.id == FinTransaction.category_id)
        .where(FinCategory.code == "DONATION")
        .order_by(FinTransaction.txn_date, FinTransaction.id)
    )
    txns = list(ctx.db.scalars(stmt))
    fams = {
        f.id: f
        for f in ctx.db.scalars(
            select(Family).where(Family.id.in_([t.family_id for t in txns if t.family_id] or [-1]))
        )
    }
    rows = []
    for t in txns:
        f = fams.get(t.family_id or 0)
        rows.append(
            {
                "date": t.txn_date,
                "code": t.code,
                "donor": t.payer_payee or (f.family_name if f else ""),
                "family": f"{f.family_name} ({f.code})" if f else "",
                "mode": t.payment_method.replace("_", " ").title(),
                "reference": t.reference_no,
                "particulars": t.description,
                "amount": money(t.amount),
            }
        )
    total = sum((r["amount"] for r in rows), ZERO)
    return Result(
        [
            Col("date", "Date", "date"),
            Col("code", "Entry"),
            Col("donor", "Donor"),
            Col("family", "Family"),
            Col("mode", "Mode"),
            Col("reference", "Reference"),
            Col("particulars", "Particulars"),
            Col("amount", "Amount ₹", "money"),
        ],
        rows,
        subtitle=f"{ctx.range_label(lo, hi)} · {len(rows)} donations",
        totals={"donor": "Total", "amount": money(total)},
    )


@report(
    "expense_category", "FINANCE", "Expense category report",
    "Expenditure per category with entries and share of the total.",
    "finance.view", (DATE_RANGE, ORG_UNIT),
)  # fmt: skip
def expense_category(ctx: Ctx) -> Result:
    lo, hi = ctx.range()
    cats = _cats(ctx)
    sums: dict[int | None, Decimal] = defaultdict(lambda: ZERO)
    cnt: dict[int | None, int] = defaultdict(int)
    for t in ctx.db.scalars(_approved(ctx, lo, hi).where(FinTransaction.kind == "EXPENSE")):
        sums[t.category_id] += t.amount
        cnt[t.category_id] += 1
    total = sum(sums.values(), ZERO)
    rows = [
        {
            "category": cats[k].name if k in cats else "—",
            "entries": cnt[k],
            "amount": money(v),
            "share": float(round(v * 100 / total, 1)) if total else 0.0,
        }
        for k, v in sorted(sums.items(), key=lambda kv: -kv[1])
    ]
    return Result(
        [
            Col("category", "Category"),
            Col("entries", "Entries", "number"),
            Col("amount", "Amount ₹", "money"),
            Col("share", "Share %", "number"),
        ],
        rows,
        subtitle=ctx.range_label(lo, hi),
        totals={
            "category": "Total",
            "entries": sum(cnt.values()),
            "amount": money(total),
            "share": 100.0 if total else 0.0,
        },
    )


@report(
    "org_financial", "FINANCE", "Organisation-wise financial statement",
    "Income, expenditure and net for the parish and each organisation.",
    "finance.view", (DATE_RANGE,),
)  # fmt: skip
def org_financial(ctx: Ctx) -> Result:
    lo, hi = ctx.range()
    names = dict(ctx.db.execute(select(OrgUnit.id, OrgUnit.name)).all())
    per: dict[int | None, dict[str, Decimal]] = defaultdict(lambda: {"INCOME": ZERO, "EXPENSE": ZERO})
    for t in ctx.db.scalars(_approved(ctx, lo, hi).where(FinTransaction.kind.in_(("INCOME", "EXPENSE")))):
        per[t.org_unit_id][t.kind] += t.amount
    rows = [
        {
            "organisation": names.get(k, "") if k else "Parish",
            "income": money(v["INCOME"]),
            "expense": money(v["EXPENSE"]),
            "net": money(v["INCOME"] - v["EXPENSE"]),
        }
        for k, v in sorted(per.items(), key=lambda kv: (kv[0] is not None, names.get(kv[0] or 0, "")))
    ]
    inc = sum((r["income"] for r in rows), ZERO)
    exp = sum((r["expense"] for r in rows), ZERO)
    return Result(
        [
            Col("organisation", "Organisation"),
            Col("income", "Income ₹", "money"),
            Col("expense", "Expenditure ₹", "money"),
            Col("net", "Net ₹", "money"),
        ],
        rows,
        subtitle=ctx.range_label(lo, hi),
        totals={
            "organisation": "Total",
            "income": money(inc),
            "expense": money(exp),
            "net": money(inc - exp),
        },
    )


@report(
    "pending_finance", "FINANCE", "Pending financial approvals",
    "Entries submitted and still waiting for approval, or returned for rework.",
    "finance.view", (ORG_UNIT,),
)  # fmt: skip
def pending_finance(ctx: Ctx) -> Result:
    stmt = select(FinTransaction).where(
        FinTransaction.is_deleted.is_(False),
        FinTransaction.status.in_(("IN_REVIEW", "REWORK")),
        ctx.scope.filter(FinTransaction.org_unit_id),
    )
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(FinTransaction.org_unit_id == u.id)
    txns = list(ctx.db.scalars(stmt.order_by(FinTransaction.submitted_at, FinTransaction.id)))
    names = dict(ctx.db.execute(select(OrgUnit.id, OrgUnit.name)).all())
    accounts = dict(ctx.db.execute(select(FinAccount.id, FinAccount.name)).all())
    today = ctx.today()
    rows = [
        {
            "code": t.code,
            "date": t.txn_date,
            "kind": t.kind.title(),
            "organisation": names.get(t.org_unit_id or 0, "Parish"),
            "account": accounts.get(t.account_id, ""),
            "particulars": t.description,
            "amount": money(t.amount),
            "status": t.status,
            "waiting_days": (today - t.submitted_at.date()).days if t.submitted_at else None,
        }
        for t in txns
    ]
    return Result(
        [
            Col("code", "Entry"),
            Col("date", "Date", "date"),
            Col("kind", "Type"),
            Col("organisation", "Organisation"),
            Col("account", "Account"),
            Col("particulars", "Particulars"),
            Col("amount", "Amount ₹", "money"),
            Col("status", "Status", "status"),
            Col("waiting_days", "Days waiting", "number"),
        ],
        rows,
        subtitle=f"{len(rows)} entries",
        totals={"particulars": "Total", "amount": money(sum((r["amount"] for r in rows), ZERO))},
    )

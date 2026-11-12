"""Statement PDF / XLSX and income receipts."""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from app.common.exports import render_pdf
from app.db.tenant import TenantDescriptor


def inr(v: str | Decimal | float | None) -> str:
    d = Decimal(str(v or 0))
    sign = "-" if d < 0 else ""
    whole, _, frac = f"{abs(d):.2f}".partition(".")
    # Indian digit grouping: 12,34,567.00
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join([*groups, tail]) if groups else tail}.{frac}"


def statement_pdf(tenant: TenantDescriptor, snap: dict[str, Any]) -> bytes:
    return render_pdf(
        "statement.html",
        {
            "title": f"Monthly Financial Statement – {snap['label']}",
            "parish_name": tenant.name,
            "s": snap,
            "inr": inr,
            "landscape": False,
        },
    )


def receipt_pdf(tenant: TenantDescriptor, ctx: dict[str, Any]) -> bytes:
    return render_pdf(
        "receipt.html", {"title": f"Receipt {ctx['code']}", "parish_name": tenant.name, "inr": inr, **ctx}
    )


def statement_xlsx(tenant: TenantDescriptor, snap: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    bold, head_fill = Font(bold=True), PatternFill("solid", fgColor="EEF0FA")
    num = "#,##,##0.00;[Red]-#,##,##0.00"

    def table(ws, top: int, headers: list[str], rows: list[list[Any]], money_cols: set[int]) -> int:  # type: ignore[no-untyped-def]
        for c, h in enumerate(headers, start=1):
            cell = ws.cell(row=top, column=c, value=h)
            cell.font, cell.fill = bold, head_fill
        for r, row in enumerate(rows, start=top + 1):
            for c, v in enumerate(row, start=1):
                cell = ws.cell(
                    row=r, column=c, value=float(v) if c in money_cols and v not in (None, "") else v
                )
                if c in money_cols:
                    cell.number_format = num
        return top + len(rows) + 2

    ws = wb.active
    ws.title = "Summary"
    ws["A1"], ws["A2"] = tenant.name, f"Monthly Financial Statement – {snap['label']}"
    ws["A1"].font, ws["A2"].font = Font(bold=True, size=13), Font(bold=True, size=12)
    ws["A3"] = f"Version {snap.get('version', 1)} · generated {snap.get('generated_at', '')}"
    if snap.get("revision_reason"):
        ws["A4"] = f"Revision: {snap['revision_reason']}"
    t = snap["totals"]
    row = table(
        ws,
        6,
        ["", "Amount (₹)"],
        [
            ["Opening balance", t["opening"]],
            ["Total income", t["income"]],
            ["Total expenditure", t["expense"]],
            ["Surplus / deficit", t["surplus"]],
            ["Closing balance", t["closing"]],
        ],
        {2},
    )
    row = table(
        ws,
        row,
        [
            "Account",
            "Kind",
            "Organisation",
            "Opening",
            "Income",
            "Expense",
            "Transfers in",
            "Transfers out",
            "Closing",
        ],
        [
            [
                a["name"],
                a["kind"],
                a["org_unit"] or "Parish",
                a["opening"],
                a["income"],
                a["expense"],
                a["transfers_in"],
                a["transfers_out"],
                a["closing"],
            ]
            for a in snap["accounts"]
        ],
        {4, 5, 6, 7, 8, 9},
    )
    ws.column_dimensions["A"].width = 32
    for col in "BCDEFGHI":
        ws.column_dimensions[col].width = 16

    cats = wb.create_sheet("Categories")
    row = table(
        cats,
        1,
        ["Income category", "Amount (₹)"],
        [[c["name"], c["amount"]] for c in snap["income_by_category"]],
        {2},
    )
    table(
        cats,
        row,
        ["Expense category", "Amount (₹)"],
        [[c["name"], c["amount"]] for c in snap["expense_by_category"]],
        {2},
    )
    cats.column_dimensions["A"].width, cats.column_dimensions["B"].width = 36, 16

    orgs = wb.create_sheet("Organisations")
    table(
        orgs,
        1,
        ["Organisation", "Type", "Income", "Expense", "Net"],
        [[o["name"], o["type"], o["income"], o["expense"], o["net"]] for o in snap["organisations"]],
        {3, 4, 5},
    )
    orgs.column_dimensions["A"].width = 32
    for ws_ in wb.worksheets:
        for r in ws_.iter_rows():
            for cell in r:
                cell.alignment = Alignment(vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

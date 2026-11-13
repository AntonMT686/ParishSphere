"""Tabular exports (CSV, XLSX, PDF) and HTML→PDF rendering.

Exports are synchronous up to ``max_export_rows``; larger exports belong in a background job.
Spreadsheet outputs neutralise formula injection (cells starting with ``= + - @``).
"""

from __future__ import annotations

import contextlib
import csv
import io
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import Response

from app.common.storage import content_disposition
from app.core.config import get_settings
from app.core.errors import ValidationFailed

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


MEDIA_TYPES = {
    ExportFormat.CSV: "text/csv; charset=utf-8",
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.PDF: "application/pdf",
}


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    width: int | None = None  # XLSX column width (characters)
    numeric: bool = False
    formatter: Callable[[Any], Any] | None = None

    def value(self, row: Any) -> Any:
        raw = row.get(self.key) if isinstance(row, dict) else getattr(row, self.key, None)
        return self.formatter(raw) if self.formatter else raw


def _plain(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, list | tuple | set):
        return ", ".join(str(v) for v in value)
    return value


def _safe_text(value: Any) -> Any:
    """Prevent CSV/Excel formula injection."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _matrix(rows: Iterable[Any], columns: Sequence[Column]) -> list[list[Any]]:
    limit = get_settings().max_export_rows
    out: list[list[Any]] = []
    for i, row in enumerate(rows):
        if i >= limit:
            raise ValidationFailed(
                f"Exports are limited to {limit} rows; narrow the filters", code="EXPORT_TOO_LARGE"
            )
        out.append([_plain(c.value(row)) for c in columns])
    return out


def to_csv(matrix: list[list[Any]], columns: Sequence[Column]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c.header for c in columns])
    for row in matrix:
        writer.writerow([_safe_text(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel opens UTF-8 (Tamil) correctly


def to_xlsx(matrix: list[list[Any]], columns: Sequence[Column], title: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = (title[:31] or "Export").replace("/", "-")
    ws.append([c.header for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEF0FA")
        cell.alignment = Alignment(vertical="center")
    for row_no, row in enumerate(matrix, start=2):  # row 1 is the header
        values: list[Any] = []
        for c, v in zip(columns, row, strict=True):
            if c.numeric and isinstance(v, str):
                with contextlib.suppress(ValueError):
                    v = float(v)
            values.append(v)
        ws.append(values)
        # Address cells directly: ``ws[ws.max_row]`` rescans the whole sheet per row (quadratic).
        for col_no, v in enumerate(values, start=1):
            if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
                ws.cell(row=row_no, column=col_no).data_type = "s"  # store as text, never as a formula
    for idx, c in enumerate(columns, start=1):
        letter = get_column_letter(idx)
        longest = max([len(str(c.header))] + [len(str(r[idx - 1])) for r in matrix[:500]] or [10])
        ws.column_dimensions[letter].width = c.width or min(max(10, longest + 2), 60)
        if c.numeric:
            for cell in ws[letter][1:]:
                cell.number_format = "#,##0.00"
    ws.freeze_panes = "A2"
    if matrix:
        ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _jinja_env():  # type: ignore[no-untyped-def]
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR / "pdf")),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["css_string"] = css_string
    return env


def css_string(value: Any) -> Any:
    """Text for a CSS ``content: "…"`` string: HTML entities are not decoded there, so the value is
    CSS-escaped instead (quotes, backslashes and ``<`` cannot end the string or the style element)."""
    from markupsafe import Markup

    text = str(value or "")
    return Markup("".join(ch if ch.isalnum() or ch in " .,-·()&'" else f"\\{ord(ch):06x}" for ch in text))  # noqa: S704 (escaped above)


def render_pdf(template: str, context: dict[str, Any]) -> bytes:
    """Render ``app/templates/pdf/<template>`` (Jinja2, autoescaped) to PDF with WeasyPrint."""
    from weasyprint import HTML

    ctx = {"generated_at": datetime.now(UTC).strftime("%d %b %Y %H:%M UTC"), **context}
    html = _jinja_env().get_template(template).render(**ctx)
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()  # type: ignore[no-any-return]


def to_pdf(
    matrix: list[list[Any]],
    columns: Sequence[Column],
    *,
    title: str,
    subtitle: str | None,
    parish_name: str,
    generated_by: str | None,
) -> bytes:
    return render_pdf(
        "table.html",
        {
            "title": title,
            "subtitle": subtitle,
            "parish_name": parish_name,
            "generated_by": generated_by,
            "columns": columns,
            "rows": matrix,
            "landscape": len(columns) > 6,
        },
    )


def export_table(
    rows: Iterable[Any],
    columns: Sequence[Column],
    fmt: ExportFormat | str,
    *,
    title: str,
    filename: str,
    parish_name: str = "",
    subtitle: str | None = None,
    generated_by: str | None = None,
) -> Response:
    """Build a download ``Response`` for ``rows`` in the requested format."""
    fmt = ExportFormat(fmt)
    matrix = _matrix(rows, columns)
    if fmt is ExportFormat.CSV:
        body = to_csv(matrix, columns)
    elif fmt is ExportFormat.XLSX:
        body = to_xlsx(matrix, columns, title)
    else:
        body = to_pdf(
            matrix,
            columns,
            title=title,
            subtitle=subtitle,
            parish_name=parish_name,
            generated_by=generated_by,
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(
        content=body,
        media_type=MEDIA_TYPES[fmt],
        headers={
            "Content-Disposition": content_disposition(f"{filename}-{stamp}.{fmt.value}"),
            "Cache-Control": "no-store",
        },
    )

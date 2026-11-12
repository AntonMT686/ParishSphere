"""Ledger rules, balances, monthly periods and statements, and the finance workflow handlers.

Accounting rules (docs/04-database-design.md §3.8):
* only APPROVED transactions affect balances and statements;
* a transaction belongs to the period (month) of its date; nothing can be entered, changed, submitted or
  approved in a month that is not OPEN;
* a month can be closed only when it has no unfinished entries and every earlier month is closed;
* corrections are entries that reference the corrected one (amount may then be negative); a released
  month can be reopened (with a reason) and produces a new statement version – earlier versions are kept.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.sequences import next_code
from app.common.storage import build_key, get_storage
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.tenant import TenantDescriptor
from app.modules.finance.models import FinAccount, FinCategory, FinPeriod, FinStatement, FinTransaction
from app.modules.identity.models import User
from app.modules.notifications.service import emit
from app.modules.org_units.models import OrgUnit
from app.modules.rbac.service import users_with_permission
from app.modules.workflow import service as wf
from app.modules.workflow.models import WorkflowInstance
from app.modules.workflow.registry import WorkflowHandler, register_handler

EDITABLE = ("DRAFT", "REWORK")
PENDING = ("DRAFT", "IN_REVIEW", "REWORK")
KINDS = ("INCOME", "EXPENSE", "TRANSFER")
METHODS = ("CASH", "CHEQUE", "BANK_TRANSFER", "UPI", "CARD", "ONLINE")
ZERO = Decimal("0.00")


def money(v: Decimal | float | int | None) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"))


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
    return start, end


# ============================================================================ periods
def period_for(db: Session, day: date, create: bool = True) -> FinPeriod | None:
    p = db.scalar(select(FinPeriod).where(FinPeriod.year == day.year, FinPeriod.month == day.month))
    if p is None and create:
        p = FinPeriod(year=day.year, month=day.month, status="OPEN")
        db.add(p)
        db.flush()
    return p


def get_period(db: Session, public_id: str) -> FinPeriod:
    p = db.scalar(select(FinPeriod).where(FinPeriod.public_id == public_id))
    if p is None:
        raise NotFound("Month not found")
    return p


def ensure_open(period: FinPeriod) -> None:
    if not period.is_open:
        raise Conflict(
            f"{period.label} is closed ({period.status.replace('_', ' ').lower()}). "
            "Entries for a closed month cannot be added or changed.",
            code="PERIOD_CLOSED",
        )


# ============================================================================ transactions
def get_txn(db: Session, public_id: str) -> FinTransaction:
    t = db.scalar(
        select(FinTransaction).where(
            FinTransaction.public_id == public_id, FinTransaction.is_deleted.is_(False)
        )
    )
    if t is None:
        raise NotFound("Transaction not found")
    return t


def validate_txn(db: Session, data: dict[str, Any]) -> None:
    """Cross-field accounting validation for a new or edited entry."""
    kind = data["kind"]
    acc = db.get(FinAccount, data["account_id"])
    if acc is None or acc.is_deleted or not acc.is_active:
        raise ValidationFailed(details=[{"field": "account_id", "message": "Choose an active account"}])
    if data["txn_date"] < acc.opening_date:
        raise ValidationFailed(
            details=[{"field": "txn_date", "message": f"{acc.name} starts on {acc.opening_date}"}]
        )
    if data["txn_date"] > date.today():
        raise ValidationFailed(details=[{"field": "txn_date", "message": "The date cannot be in the future"}])
    if acc.org_unit_id is not None and acc.org_unit_id != data.get("org_unit_id"):
        raise ValidationFailed(
            details=[{"field": "account_id", "message": "This account belongs to another organisation"}]
        )
    adjusts = data.get("adjusts_transaction_id")
    if data["amount"] == 0 or (data["amount"] < 0 and not adjusts):
        raise ValidationFailed(details=[{"field": "amount", "message": "Enter a positive amount"}])
    if kind == "TRANSFER":
        if data.get("category_id"):
            raise ValidationFailed(
                details=[{"field": "category_id", "message": "Transfers have no category"}]
            )
        to = db.get(FinAccount, data.get("to_account_id")) if data.get("to_account_id") else None
        if to is None or not to.is_active or to.id == acc.id:
            raise ValidationFailed(
                details=[{"field": "to_account_id", "message": "Choose another active account"}]
            )
        if data["amount"] < 0:
            raise ValidationFailed(details=[{"field": "amount", "message": "Enter a positive amount"}])
    else:
        cat = db.get(FinCategory, data.get("category_id")) if data.get("category_id") else None
        if cat is None or not cat.is_active or cat.kind != kind:
            raise ValidationFailed(
                details=[{"field": "category_id", "message": f"Choose an {kind.lower()} category"}]
            )
        if data.get("to_account_id"):
            raise ValidationFailed(
                details=[{"field": "to_account_id", "message": "Only transfers have a target"}]
            )
    if adjusts:
        orig = db.get(FinTransaction, adjusts)
        if orig is None or orig.status != "APPROVED" or orig.kind != kind:
            raise ValidationFailed(
                details=[
                    {
                        "field": "adjusts_transaction_id",
                        "message": "Correct an approved entry of the same kind",
                    }
                ]
            )
    ensure_open(period_for(db, data["txn_date"]))  # type: ignore[arg-type]


def new_txn(db: Session, data: dict[str, Any], actor_id: int) -> FinTransaction:
    validate_txn(db, data)
    period = period_for(db, data["txn_date"])
    assert period
    t = FinTransaction(
        code=next_code(db, "TRANSACTION", data["txn_date"]),
        period_id=period.id,
        status="DRAFT",
        created_by=actor_id,
        **data,
    )
    db.add(t)
    db.flush()
    return t


def update_txn(db: Session, t: FinTransaction, data: dict[str, Any], actor_id: int) -> None:
    if t.status not in EDITABLE:
        raise Conflict("Only drafts and entries returned for rework can be changed", code="NOT_EDITABLE")
    ensure_open(db.get(FinPeriod, t.period_id))  # type: ignore[arg-type]
    validate_txn(db, data)
    period = period_for(db, data["txn_date"])
    assert period
    for k, v in data.items():
        setattr(t, k, v)
    t.period_id, t.updated_by = period.id, actor_id


def _ctx(db: Session, t: FinTransaction) -> dict[str, Any]:
    cat = db.get(FinCategory, t.category_id) if t.category_id else None
    return {"amount": float(abs(t.amount)), "category": cat.code if cat else t.kind}


def txn_title(db: Session, t: FinTransaction) -> str:
    cat = db.get(FinCategory, t.category_id) if t.category_id else None
    what = cat.name if cat else "Transfer"
    return f"{t.code} · {what} ₹{abs(t.amount):,.2f} – {t.description[:80]}"


def submit_txn(
    db: Session, tenant: TenantDescriptor, t: FinTransaction, actor_id: int, comment: str | None = None
) -> WorkflowInstance:
    ensure_open(db.get(FinPeriod, t.period_id))  # type: ignore[arg-type]
    if t.status == "REWORK":
        inst = wf.active_instance(db, "FIN_TRANSACTION", t.public_id)
        if inst is None:
            raise Conflict("No approval is waiting for this entry", code="INVALID_STATE")
        return wf.resubmit(db, tenant, inst, actor_id, comment, title=txn_title(db, t), context=_ctx(db, t))
    if t.status != "DRAFT":
        raise Conflict("Only drafts can be submitted", code="INVALID_STATE")
    return wf.submit(
        db,
        tenant,
        entity_type="FIN_TRANSACTION",
        entity_id=t.public_id,
        title=txn_title(db, t),
        actor_id=actor_id,
        org_unit_id=t.org_unit_id,
        context=_ctx(db, t),
        link=f"/finance/transactions/{t.public_id}",
        comment=comment,
    )


def _txn_status(status: str):  # type: ignore[no-untyped-def]
    def cb(db: Session, inst: WorkflowInstance) -> None:
        t = get_txn(db, inst.entity_id)
        if status == "APPROVED":
            # The month may have been closed while the entry waited – it would change a statement.
            ensure_open(db.get(FinPeriod, t.period_id))  # type: ignore[arg-type]
            approvals = _approvals(db, inst)
            t.reviewed_by = approvals[0] if len(approvals) > 1 else None
            t.approved_by = approvals[-1] if approvals else None
            t.approved_at = utcnow()
        elif status == "IN_REVIEW":
            t.submitted_at = utcnow()
        t.status = status

    return cb


def _approvals(db: Session, inst: WorkflowInstance) -> list[int | None]:
    """Approvers of this cycle in order (queried: the final approval is not in ``inst.actions`` yet)."""
    from app.modules.workflow.models import WorkflowAction

    return list(
        db.scalars(
            select(WorkflowAction.actor_id)
            .where(
                WorkflowAction.instance_id == inst.id,
                WorkflowAction.cycle == inst.cycle,
                WorkflowAction.action == "APPROVE",
            )
            .order_by(WorkflowAction.id)
        )
    )


register_handler(
    "FIN_TRANSACTION",
    WorkflowHandler(
        on_submitted=_txn_status("IN_REVIEW"),
        on_approved=_txn_status("APPROVED"),
        on_rejected=_txn_status("REJECTED"),
        on_rework=_txn_status("REWORK"),
        on_withdrawn=_txn_status("DRAFT"),
    ),
)


# ============================================================================ balances & statements
def _approved_in(db: Session, start: date | None, end: date) -> list[FinTransaction]:
    stmt = select(FinTransaction).where(
        FinTransaction.status == "APPROVED",
        FinTransaction.is_deleted.is_(False),
        FinTransaction.txn_date <= end,
    )
    if start:
        stmt = stmt.where(FinTransaction.txn_date >= start)
    return list(db.scalars(stmt))


def balances(db: Session, on: date, account_ids: set[int] | None = None) -> dict[int, Decimal]:
    """Closing balance of every account at the end of ``on``."""
    accounts = db.scalars(select(FinAccount).where(FinAccount.is_deleted.is_(False))).all()
    out = {a.id: (a.opening_balance if a.opening_date <= on else ZERO) for a in accounts}
    for t in _approved_in(db, None, on):
        for acc in (t.account_id, t.to_account_id):
            if acc is not None and acc in out:
                out[acc] += t.effect(acc)
    if account_ids is not None:
        out = {k: v for k, v in out.items() if k in account_ids}
    return {k: money(v) for k, v in out.items()}


def build_snapshot(db: Session, year: int, month: int) -> dict[str, Any]:
    """Everything a monthly statement shows, computed from approved entries."""
    start, end = month_bounds(year, month)
    accounts = db.scalars(
        select(FinAccount)
        .where(FinAccount.is_deleted.is_(False), FinAccount.opening_date <= end)
        .order_by(FinAccount.code)
    ).all()
    opening = balances(db, start - timedelta(days=1))
    rows = []
    month_txns = _approved_in(db, start, end)
    for a in accounts:
        op = opening.get(a.id, ZERO)
        if start <= a.opening_date <= end:
            op = money(a.opening_balance)  # account opened during this month
        inc = sum((t.amount for t in month_txns if t.kind == "INCOME" and t.account_id == a.id), ZERO)
        exp = sum((t.amount for t in month_txns if t.kind == "EXPENSE" and t.account_id == a.id), ZERO)
        tin = sum((t.amount for t in month_txns if t.kind == "TRANSFER" and t.to_account_id == a.id), ZERO)
        tout = sum((t.amount for t in month_txns if t.kind == "TRANSFER" and t.account_id == a.id), ZERO)
        if not a.is_active and op == 0 and not (inc or exp or tin or tout):
            continue
        unit = db.get(OrgUnit, a.org_unit_id) if a.org_unit_id else None
        rows.append(
            {
                "code": a.code,
                "name": a.name,
                "kind": a.kind,
                "org_unit": unit.name if unit else None,
                "opening": str(money(op)),
                "income": str(money(inc)),
                "expense": str(money(exp)),
                "transfers_in": str(money(tin)),
                "transfers_out": str(money(tout)),
                "closing": str(money(op + inc - exp + tin - tout)),
            }
        )
    cats = {c.id: c for c in db.scalars(select(FinCategory))}
    by_cat: dict[tuple[str, int], Decimal] = defaultdict(lambda: ZERO)
    by_unit: dict[int | None, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for t in month_txns:
        if t.kind == "TRANSFER":
            continue
        by_cat[(t.kind, t.category_id or 0)] += t.amount
        by_unit[t.org_unit_id][0 if t.kind == "INCOME" else 1] += t.amount

    def cat_rows(kind: str) -> list[dict[str, str]]:
        items = [(cats[cid], amt) for (k, cid), amt in by_cat.items() if k == kind and cid in cats]
        items.sort(key=lambda x: (x[0].sort_order, x[0].name))
        return [{"code": c.code, "name": c.name, "amount": str(money(a))} for c, a in items]

    units = []
    for uid, (inc, exp) in sorted(by_unit.items(), key=lambda kv: (kv[0] is not None, kv[0] or 0)):
        u = db.get(OrgUnit, uid) if uid else None
        units.append(
            {
                "name": u.name if u else "Parish",
                "type": u.type.name if u else "",
                "income": str(money(inc)),
                "expense": str(money(exp)),
                "net": str(money(inc - exp)),
            }
        )
    pending = db.scalars(
        select(FinTransaction)
        .where(
            FinTransaction.is_deleted.is_(False),
            FinTransaction.status.in_(PENDING),
            FinTransaction.txn_date >= start,
            FinTransaction.txn_date <= end,
        )
        .order_by(FinTransaction.txn_date)
    ).all()
    income = sum((t.amount for t in month_txns if t.kind == "INCOME"), ZERO)
    expense = sum((t.amount for t in month_txns if t.kind == "EXPENSE"), ZERO)
    total_open = sum((Decimal(r["opening"]) for r in rows), ZERO)
    return {
        "year": year,
        "month": month,
        "label": date(year, month, 1).strftime("%B %Y"),
        "from": start.isoformat(),
        "to": end.isoformat(),
        "totals": {
            "opening": str(money(total_open)),
            "income": str(money(income)),
            "expense": str(money(expense)),
            "surplus": str(money(income - expense)),
            "closing": str(money(total_open + income - expense)),
        },
        "accounts": rows,
        "income_by_category": cat_rows("INCOME"),
        "expense_by_category": cat_rows("EXPENSE"),
        "organisations": units,
        "transactions": len(month_txns),
        "pending": [
            {
                "code": t.code,
                "date": t.txn_date.isoformat(),
                "kind": t.kind,
                "amount": str(money(t.amount)),
                "description": t.description[:120],
                "status": t.status,
            }
            for t in pending
        ],
    }


def close_period(
    db: Session, tenant: TenantDescriptor, p: FinPeriod, actor_id: int, comment: str | None = None
) -> WorkflowInstance:
    """Treasurer closes the month and sends it for approval."""
    if p.status != "OPEN":
        raise Conflict(f"{p.label} is not open", code="INVALID_STATE")
    start, end = month_bounds(p.year, p.month)
    if end >= date.today():
        raise Conflict(f"{p.label} has not ended yet", code="PERIOD_NOT_ENDED")
    earlier = db.scalar(
        select(FinPeriod)
        .where(
            FinPeriod.status == "OPEN",  # months under review are already locked
            or_(FinPeriod.year < p.year, (FinPeriod.year == p.year) & (FinPeriod.month < p.month)),
        )
        .order_by(FinPeriod.year, FinPeriod.month)
    )
    if earlier is not None and _has_entries(db, earlier):
        raise Conflict(f"Close {earlier.label} first", code="EARLIER_PERIOD_OPEN")
    pending = db.scalar(
        select(func.count())
        .select_from(FinTransaction)
        .where(
            FinTransaction.period_id == p.id,
            FinTransaction.status.in_(PENDING),
            FinTransaction.is_deleted.is_(False),
        )
    )
    if pending:
        raise Conflict(
            f"{pending} entr{'y' if pending == 1 else 'ies'} of {p.label} still need a decision "
            "(draft, under review or returned)",
            code="PENDING_ENTRIES",
        )
    inst = active = wf.active_instance(db, "FIN_PERIOD", p.public_id)
    if active is not None and active.status == "REWORK":
        inst = wf.resubmit(db, tenant, active, actor_id, comment, title=f"Monthly statement · {p.label}")
    else:
        inst = wf.submit(
            db,
            tenant,
            entity_type="FIN_PERIOD",
            entity_id=p.public_id,
            title=f"Monthly statement · {p.label}",
            actor_id=actor_id,
            link=f"/finance/statements/{p.year:04d}-{p.month:02d}",
            comment=comment,
        )
    p.submitted_by = actor_id
    return inst


def _has_entries(db: Session, p: FinPeriod) -> bool:
    return bool(
        db.scalar(
            select(FinTransaction.id)
            .where(FinTransaction.period_id == p.id, FinTransaction.is_deleted.is_(False))
            .limit(1)
        )
    )


def generate_statement(
    db: Session, tenant: TenantDescriptor, p: FinPeriod, actor_id: int | None
) -> FinStatement:
    from app.modules.finance.documents import statement_pdf, statement_xlsx

    snap = build_snapshot(db, p.year, p.month)
    prev = db.scalars(select(FinStatement).where(FinStatement.period_id == p.id)).all()
    version = max((s.version for s in prev), default=0) + 1
    snap["version"] = version
    snap["revision_reason"] = p.revision_reason if version > 1 else None
    snap["generated_at"] = utcnow().isoformat(timespec="seconds")
    pdf = statement_pdf(tenant, snap)
    xlsx = statement_xlsx(tenant, snap)
    storage = get_storage()
    pdf_key, xlsx_key = (
        build_key(tenant.code, "statements", "pdf"),
        build_key(tenant.code, "statements", "xlsx"),
    )
    storage.put(pdf_key, pdf, "application/pdf")
    storage.put(xlsx_key, xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for s in prev:
        s.is_current = False
    st = FinStatement(
        period_id=p.id,
        version=version,
        snapshot=snap,
        pdf_key=pdf_key,
        xlsx_key=xlsx_key,
        sha256=hashlib.sha256(pdf).hexdigest(),
        generated_by=actor_id,
        is_current=True,
        revision_reason=snap["revision_reason"],
    )
    db.add(st)
    db.flush()
    return st


def _period_status(status: str):  # type: ignore[no-untyped-def]
    def cb(db: Session, inst: WorkflowInstance) -> None:
        p = get_period(db, inst.entity_id)
        p.status = status
        if status == "UNDER_REVIEW":
            p.submitted_at = utcnow()
        elif status == "APPROVED":
            p.approved_at = utcnow()
            approvals = _approvals(db, inst)
            tenant = db.info.get("tenant")
            if tenant is None:  # pragma: no cover - the engine always sets it
                raise RuntimeError("tenant missing on session")
            generate_statement(db, tenant, p, approvals[-1] if approvals else None)

    return cb


register_handler(
    "FIN_PERIOD",
    WorkflowHandler(
        on_submitted=_period_status("UNDER_REVIEW"),
        on_approved=_period_status("APPROVED"),
        on_rejected=_period_status("OPEN"),
        on_rework=_period_status("OPEN"),
        on_withdrawn=_period_status("OPEN"),
    ),
)


def release(db: Session, tenant: TenantDescriptor, p: FinPeriod, actor_id: int) -> FinStatement:
    if p.status != "APPROVED":
        raise Conflict("Only approved statements can be released", code="INVALID_STATE")
    st = current_statement(db, p)
    if st is None:
        raise Conflict("The statement has not been generated", code="INVALID_STATE")
    now = utcnow()
    p.status, p.released_at, p.released_by, p.revision_reason = "RELEASED", now, actor_id, None
    st.released_at = now
    recipients = users_with_permission(db, "finance_period.view") + users_with_permission(
        db, "finance.view_summary"
    )
    emit(
        db,
        tenant,
        "statement.released",
        recipients,
        {"period": p.label},
        link=f"/finance/statements/{p.year:04d}-{p.month:02d}",
        entity_type="FIN_PERIOD",
        entity_id=p.public_id,
        exclude_user_id=actor_id,
    )
    return st


def reopen(db: Session, p: FinPeriod, actor_id: int, reason: str) -> None:
    """Reopen the latest released month for corrections; its next statement becomes a new version."""
    if p.status != "RELEASED":
        raise Conflict("Only released months can be reopened", code="INVALID_STATE")
    later = db.scalar(
        select(FinPeriod).where(
            FinPeriod.status != "OPEN",
            or_(FinPeriod.year > p.year, (FinPeriod.year == p.year) & (FinPeriod.month > p.month)),
        )
    )
    if later is not None:
        raise Conflict(
            f"{later.label} is already closed; corrections must go in the latest month",
            code="LATER_PERIOD_CLOSED",
        )
    p.status, p.revision_reason = "OPEN", reason
    p.approved_at = p.released_at = p.submitted_at = None


def current_statement(db: Session, p: FinPeriod) -> FinStatement | None:
    return db.scalar(
        select(FinStatement).where(FinStatement.period_id == p.id, FinStatement.is_current.is_(True))
    )


def user_name(db: Session, user_id: int | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.full_name if u else None

"""Finance (``/api/v1/finance``): accounts, categories, transactions, monthly periods & statements."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import changes, record_audit
from app.common.exports import Column, ExportFormat, export_table
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.common.storage import content_disposition, get_storage
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.modules.attachments.service import AttachmentOut, add_attachment, list_attachments, remove_attachment
from app.modules.finance import service as svc
from app.modules.finance.documents import receipt_pdf
from app.modules.finance.models import FinAccount, FinCategory, FinPeriod, FinStatement, FinTransaction
from app.modules.finance.schemas import (
    AccountIn,
    AccountOut,
    AccountUpdate,
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    DownloadOut,
    FinRef,
    PeriodListOut,
    PeriodOut,
    ReopenIn,
    StatementVersion,
    SubmitIn,
    SummaryOut,
    TxnIn,
    TxnListOut,
    TxnOut,
)
from app.modules.identity.deps import Auth
from app.modules.org_units.models import OrgUnit
from app.modules.people.models import Family
from app.modules.rbac.deps import require_any, require_perm
from app.modules.rbac.service import PermissionScope
from app.modules.workflow.models import WorkflowInstance
from app.tenancy.deps import TenantSession

router = APIRouter(prefix="/finance", tags=["finance"])
MODULE = "finance"


def _p(code: str, parish_wide: bool = False):  # type: ignore[no-untyped-def]
    return Annotated[PermissionScope, Depends(require_perm(code, parish_wide=parish_wide))]


View, Create, Update, Delete, Submit, Export = (
    _p("finance.view"),
    _p("finance.create"),
    _p("finance.update"),
    _p("finance.delete"),
    _p("finance.submit"),
    _p("finance.export"),
)
Configure = _p("finance.configure", True)
PeriodView, PeriodSubmit, PeriodRelease = (
    _p("finance_period.view", True),
    _p("finance_period.submit", True),
    _p("finance_period.release", True),
)


def _audit(
    db: Session, auth: Auth, request: Request | None, action: str, entity: str, entity_id: str, **kw: Any
) -> None:
    record_audit(
        db,
        action=action,
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type=entity,
        entity_id=entity_id,
        **kw,
    )


class Names:
    def __init__(self, db: Session) -> None:
        self.db, self.cache = db, {}  # type: ignore[var-annotated]

    def get(self, model: Any, pk: int | None, label: str = "name") -> FinRef | None:
        if pk is None:
            return None
        key = (model, pk)
        if key not in self.cache:
            row = self.db.get(model, pk)
            self.cache[key] = FinRef(id=row.public_id, name=getattr(row, label)) if row else None
        return self.cache[key]  # type: ignore[no-any-return]


def _pid(db: Session, model: Any, public_id: str | None, what: str) -> int | None:
    if not public_id:
        return None
    pk = db.scalar(select(model.id).where(model.public_id == public_id))
    if pk is None:
        raise NotFound(f"{what} not found")
    return pk  # type: ignore[no-any-return]


# ============================================================================ accounts
def _account_out(db: Session, a: FinAccount, bal: dict[int, Decimal] | None, names: Names) -> AccountOut:
    pending = (
        db.scalar(
            select(func.count())
            .select_from(FinTransaction)
            .where(
                or_(FinTransaction.account_id == a.id, FinTransaction.to_account_id == a.id),
                FinTransaction.status.in_(svc.PENDING),
                FinTransaction.is_deleted.is_(False),
            )
        )
        or 0
    )
    return AccountOut(
        id=a.public_id,
        code=a.code,
        name=a.name,
        kind=a.kind,
        org_unit=names.get(OrgUnit, a.org_unit_id),
        bank_name=a.bank_name,
        account_number_masked=a.account_number_masked,
        opening_balance=a.opening_balance,
        opening_date=a.opening_date,
        is_active=a.is_active,
        balance=bal.get(a.id) if bal is not None else None,
        pending=pending,
    )


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    auth: Auth,
    db: TenantSession,
    _: Annotated[list[PermissionScope], Depends(require_any("finance.view", "finance.create"))],
    include_inactive: bool = False,
) -> list[AccountOut]:
    """Accounts the user may use (their organisations' and, with a parish-wide grant, the parish's)."""
    scope = auth.permissions.scope("finance.view")
    create = auth.permissions.scope("finance.create")
    stmt = (
        select(FinAccount)
        .where(
            FinAccount.is_deleted.is_(False),
            or_(scope.filter(FinAccount.org_unit_id), create.filter(FinAccount.org_unit_id)),
        )
        .order_by(FinAccount.org_unit_id.is_not(None), FinAccount.code)
    )
    if not include_inactive:
        stmt = stmt.where(FinAccount.is_active.is_(True))
    rows = db.scalars(stmt).all()
    bal = svc.balances(db, date.today()) if scope.granted else None
    names = Names(db)
    return [_account_out(db, a, bal if bal and scope.allows(a.org_unit_id) else None, names) for a in rows]


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountIn, request: Request, auth: Auth, _: Configure, db: TenantSession
) -> AccountOut:
    if db.scalar(select(FinAccount.id).where(FinAccount.code == body.code)):
        raise Conflict("This account code is already used", code="CODE_EXISTS")
    a = FinAccount(
        **body.model_dump(exclude={"org_unit_id"}),
        org_unit_id=_pid(db, OrgUnit, body.org_unit_id, "Organisation"),
        created_by=auth.user.id,
    )
    db.add(a)
    db.flush()
    _audit(db, auth, request, "CREATE", "fin_account", a.code, new=body.model_dump(mode="json"))
    return _account_out(db, a, svc.balances(db, date.today()), Names(db))


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: str, body: AccountUpdate, request: Request, auth: Auth, _: Configure, db: TenantSession
) -> AccountOut:
    a = db.scalar(
        select(FinAccount).where(FinAccount.public_id == account_id, FinAccount.is_deleted.is_(False))
    )
    if a is None:
        raise NotFound("Account not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_active") is False and _account_out(db, a, None, Names(db)).pending:
        raise Conflict("Decide the pending entries of this account first", code="PENDING_ENTRIES")
    for k, v in data.items():
        setattr(a, k, v)
    old, new = changes(a)
    a.updated_by = auth.user.id
    _audit(db, auth, request, "UPDATE", "fin_account", a.code, old=old, new=new)
    return _account_out(db, a, svc.balances(db, date.today()), Names(db))


# ============================================================================ categories
def _cat_out(c: FinCategory) -> CategoryOut:
    return CategoryOut(
        id=c.public_id,
        code=c.code,
        name=c.name,
        name_local=c.name_local,
        kind=c.kind,
        sort_order=c.sort_order,
        is_active=c.is_active,
        is_system=c.is_system,
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(
    db: TenantSession,
    _: Annotated[
        list[PermissionScope], Depends(require_any("finance.view", "finance.create", "finance.view_summary"))
    ],
    include_inactive: bool = False,
) -> list[CategoryOut]:
    stmt = (
        select(FinCategory)
        .where(FinCategory.is_deleted.is_(False))
        .order_by(FinCategory.kind, FinCategory.sort_order)
    )
    if not include_inactive:
        stmt = stmt.where(FinCategory.is_active.is_(True))
    return [_cat_out(c) for c in db.scalars(stmt)]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryIn, request: Request, auth: Auth, _: Configure, db: TenantSession
) -> CategoryOut:
    if db.scalar(select(FinCategory.id).where(FinCategory.code == body.code)):
        raise Conflict("This category code is already used", code="CODE_EXISTS")
    c = FinCategory(**body.model_dump(), created_by=auth.user.id)
    db.add(c)
    db.flush()
    _audit(db, auth, request, "CREATE", "fin_category", c.code, new=body.model_dump())
    return _cat_out(c)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: str, body: CategoryUpdate, request: Request, auth: Auth, _: Configure, db: TenantSession
) -> CategoryOut:
    c = db.scalar(select(FinCategory).where(FinCategory.public_id == category_id))
    if c is None:
        raise NotFound("Category not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    old, new = changes(c)
    _audit(db, auth, request, "UPDATE", "fin_category", c.code, old=old, new=new)
    return _cat_out(c)


# ============================================================================ transactions
def _txn_list_out(t: FinTransaction, n: Names) -> TxnListOut:
    return TxnListOut(
        id=t.public_id,
        code=t.code,
        txn_date=t.txn_date,
        kind=t.kind,
        category=n.get(FinCategory, t.category_id),
        account=n.get(FinAccount, t.account_id),
        to_account=n.get(FinAccount, t.to_account_id),  # type: ignore[arg-type]
        org_unit=n.get(OrgUnit, t.org_unit_id),
        amount=t.amount,
        payment_method=t.payment_method,
        description=t.description,
        payer_payee=t.payer_payee,
        status=t.status,
        is_correction=t.adjusts_transaction_id is not None,
    )


def _txn_out(db: Session, auth: Auth, t: FinTransaction) -> TxnOut:
    n = Names(db)
    period = db.get(FinPeriod, t.period_id)
    assert period
    unit = t.org_unit_id
    upd, sub, dele, create = (
        auth.permissions.scope(c).allows(unit)
        for c in ("finance.update", "finance.submit", "finance.delete", "finance.create")
    )
    corrections = db.scalars(
        select(FinTransaction).where(
            FinTransaction.adjusts_transaction_id == t.id, FinTransaction.is_deleted.is_(False)
        )
    ).all()
    editable = t.status in svc.EDITABLE and period.is_open
    approval = db.scalar(
        select(WorkflowInstance.public_id)
        .where(WorkflowInstance.entity_type == "FIN_TRANSACTION", WorkflowInstance.entity_id == t.public_id)
        .order_by(WorkflowInstance.id.desc())
        .limit(1)
    )
    return TxnOut(
        **_txn_list_out(t, n).model_dump(),
        reference_no=t.reference_no,
        family=n.get(Family, t.family_id, "family_name"),
        period=period.label,
        period_status=period.status,
        adjusts=n.get(FinTransaction, t.adjusts_transaction_id, "code"),
        corrections=[FinRef(id=c.public_id, name=c.code) for c in corrections],
        entered_by=svc.user_name(db, t.created_by),
        reviewed_by=svc.user_name(db, t.reviewed_by),
        approved_by=svc.user_name(db, t.approved_by),
        created_at=t.created_at,
        submitted_at=t.submitted_at,
        approved_at=t.approved_at,
        approval_id=approval,
        can_edit=upd and editable,
        can_submit=sub and editable,
        can_delete=dele and t.status == "DRAFT" and period.is_open,
        can_correct=create and t.status == "APPROVED" and t.kind != "TRANSFER",
        can_attach=upd and t.status not in ("REJECTED", "VOID") and period.status != "RELEASED",
    )


def _txn_fields(db: Session, body: TxnIn) -> dict[str, Any]:
    data = body.model_dump(
        exclude={
            "org_unit_id",
            "category_id",
            "account_id",
            "to_account_id",
            "family_id",
            "adjusts_transaction_id",
        }
    )
    data["org_unit_id"] = _pid(db, OrgUnit, body.org_unit_id, "Organisation")
    data["category_id"] = _pid(db, FinCategory, body.category_id, "Category")
    data["account_id"] = _pid(db, FinAccount, body.account_id, "Account")
    data["to_account_id"] = _pid(db, FinAccount, body.to_account_id, "Account")
    data["family_id"] = _pid(db, Family, body.family_id, "Family")
    data["adjusts_transaction_id"] = _pid(db, FinTransaction, body.adjusts_transaction_id, "Transaction")
    return data


def _check_accounts(db: Session, scope: PermissionScope, data: dict[str, Any]) -> None:
    """The user must be allowed to post to the accounts used (parish accounts need a parish-wide grant)."""
    for field in ("account_id", "to_account_id"):
        acc = db.get(FinAccount, data[field]) if data.get(field) else None
        if acc is not None and not scope.allows(acc.org_unit_id):
            raise ValidationFailed(details=[{"field": field, "message": "You cannot use this account"}])


def _visible(db: Session, auth: Auth, public_id: str) -> FinTransaction:
    t = svc.get_txn(db, public_id)
    if not (
        auth.permissions.scope("finance.view").allows(t.org_unit_id)
        or (t.created_by == auth.user.id and auth.permissions.scope("finance.create").allows(t.org_unit_id))
    ):
        raise NotFound("Transaction not found")
    return t


def _txn_query(
    auth: Auth,
    db: Session,
    q: str | None,
    kind: str | None,
    status_: str | None,
    category: str | None,
    account: str | None,
    org_unit: str | None,
    date_from: date | None,
    date_to: date | None,
    period: str | None,
) -> Select[Any]:
    view, create = auth.permissions.scope("finance.view"), auth.permissions.scope("finance.create")
    stmt = select(FinTransaction).where(
        FinTransaction.is_deleted.is_(False),
        or_(
            view.filter(FinTransaction.org_unit_id),
            (FinTransaction.created_by == auth.user.id) & create.filter(FinTransaction.org_unit_id),
        ),
    )
    if kind:
        stmt = stmt.where(FinTransaction.kind == kind)
    if status_ == "PENDING":
        stmt = stmt.where(FinTransaction.status.in_(svc.PENDING))
    elif status_:
        stmt = stmt.where(FinTransaction.status.in_(status_.split(",")))
    if category:
        stmt = stmt.where(FinTransaction.category_id == _pid(db, FinCategory, category, "Category"))
    if account:
        acc = _pid(db, FinAccount, account, "Account")
        stmt = stmt.where(or_(FinTransaction.account_id == acc, FinTransaction.to_account_id == acc))
    if org_unit == "PARISH":
        stmt = stmt.where(FinTransaction.org_unit_id.is_(None))
    elif org_unit:
        stmt = stmt.where(FinTransaction.org_unit_id == _pid(db, OrgUnit, org_unit, "Organisation"))
    if period:
        y, m = _key(period)
        start, end = svc.month_bounds(y, m)
        stmt = stmt.where(FinTransaction.txn_date >= start, FinTransaction.txn_date <= end)
    if date_from:
        stmt = stmt.where(FinTransaction.txn_date >= date_from)
    if date_to:
        stmt = stmt.where(FinTransaction.txn_date <= date_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                FinTransaction.code.ilike(like),
                FinTransaction.description.ilike(like),
                FinTransaction.payer_payee.ilike(like),
                FinTransaction.reference_no.ilike(like),
            )
        )
    return stmt


TxnFilters = Annotated[str | None, Query(max_length=100)]


@router.get("/transactions", response_model=Page[TxnListOut])
def list_transactions(
    auth: Auth,
    db: TenantSession,
    params: PageQuery,
    _: Annotated[list[PermissionScope], Depends(require_any("finance.view", "finance.create"))],
    q: TxnFilters = None,
    kind: TxnFilters = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    category: TxnFilters = None,
    account: TxnFilters = None,
    org_unit: TxnFilters = None,
    date_from: date | None = None,
    date_to: date | None = None,
    period: TxnFilters = None,
) -> Page[TxnListOut]:
    stmt = _txn_query(auth, db, q, kind, status_, category, account, org_unit, date_from, date_to, period)
    stmt = apply_sort(
        stmt,
        params.sort,
        {"txn_date": FinTransaction.txn_date, "amount": FinTransaction.amount, "code": FinTransaction.code},
        [FinTransaction.txn_date.desc(), FinTransaction.id.desc()],
    )
    n = Names(db)
    return paginate(db, stmt, params, lambda t: _txn_list_out(t, n))


@router.get("/transactions/export")
def export_transactions(
    auth: Auth,
    db: TenantSession,
    request: Request,
    _: Export,
    q: TxnFilters = None,
    kind: TxnFilters = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    category: TxnFilters = None,
    account: TxnFilters = None,
    org_unit: TxnFilters = None,
    date_from: date | None = None,
    date_to: date | None = None,
    period: TxnFilters = None,
    format: ExportFormat = ExportFormat.XLSX,
) -> Response:
    n = Names(db)
    rows = []
    for t in db.scalars(
        _txn_query(
            auth, db, q, kind, status_, category, account, org_unit, date_from, date_to, period
        ).order_by(FinTransaction.txn_date, FinTransaction.id)
    ):
        o = _txn_list_out(t, n)
        rows.append(
            {
                **o.model_dump(),
                "category": o.category.name if o.category else "Transfer",
                "account": o.account.name,
                "org": o.org_unit.name if o.org_unit else "Parish",
                "income": t.amount if t.kind == "INCOME" else None,
                "expense": t.amount if t.kind == "EXPENSE" else None,
            }
        )
    cols = [
        Column("code", "Transaction", 16),
        Column("txn_date", "Date", 11),
        Column("org", "Organisation", 22),
        Column("category", "Category", 22),
        Column("description", "Particulars", 40),
        Column("payer_payee", "Party", 20),
        Column("account", "Account", 18),
        Column("payment_method", "Mode", 12),
        Column("income", "Income (₹)", 13, numeric=True),
        Column("expense", "Expense (₹)", 13, numeric=True),
        Column("status", "Status", 11),
    ]
    _audit(db, auth, request, "EXPORT", "fin_transaction", "*", remarks=f"{len(rows)} rows, {format.value}")
    return export_table(
        rows,
        cols,
        format,
        title="Transactions",
        filename="transactions",
        parish_name=auth.tenant.name,
        generated_by=auth.user.full_name,
    )


@router.post("/transactions", response_model=TxnOut, status_code=status.HTTP_201_CREATED)
def create_transaction(body: TxnIn, request: Request, auth: Auth, scope: Create, db: TenantSession) -> TxnOut:
    data = _txn_fields(db, body)
    if not scope.allows(data["org_unit_id"]):
        raise PermissionDenied(details=[{"field": "permission", "message": "finance.create"}])
    _check_accounts(db, scope, data)
    t = svc.new_txn(db, data, auth.user.id)
    _audit(db, auth, request, "CREATE", "fin_transaction", t.code, new=body.model_dump(mode="json"))
    return _txn_out(db, auth, t)


@router.get("/transactions/{txn_id}", response_model=TxnOut)
def get_transaction(txn_id: str, auth: Auth, db: TenantSession) -> TxnOut:
    return _txn_out(db, auth, _visible(db, auth, txn_id))


@router.put("/transactions/{txn_id}", response_model=TxnOut)
def update_transaction(
    txn_id: str, body: TxnIn, request: Request, auth: Auth, scope: Update, db: TenantSession
) -> TxnOut:
    t = _visible(db, auth, txn_id)
    data = _txn_fields(db, body)
    if not (scope.allows(t.org_unit_id) and scope.allows(data["org_unit_id"])):
        raise PermissionDenied(details=[{"field": "permission", "message": "finance.update"}])
    _check_accounts(db, scope, data)
    if data["org_unit_id"] != t.org_unit_id and t.status != "DRAFT":
        raise Conflict("The organisation cannot change once the entry was submitted", code="NOT_EDITABLE")
    svc.update_txn(db, t, data, auth.user.id)
    old, new = changes(t)
    _audit(db, auth, request, "UPDATE", "fin_transaction", t.code, old=old, new=new)
    return _txn_out(db, auth, t)


@router.delete("/transactions/{txn_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_transaction(txn_id: str, request: Request, auth: Auth, scope: Delete, db: TenantSession) -> None:
    t = _visible(db, auth, txn_id)
    if not scope.allows(t.org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": "finance.delete"}])
    if t.status != "DRAFT":
        raise Conflict("Only drafts can be deleted", code="NOT_EDITABLE")
    svc.ensure_open(db.get(FinPeriod, t.period_id))  # type: ignore[arg-type]
    t.status = "VOID"
    t.soft_delete(auth.user.id)
    _audit(db, auth, request, "DELETE", "fin_transaction", t.code)


@router.post("/transactions/{txn_id}/submit", response_model=TxnOut)
def submit_transaction(txn_id: str, body: SubmitIn, auth: Auth, scope: Submit, db: TenantSession) -> TxnOut:
    t = _visible(db, auth, txn_id)
    if not scope.allows(t.org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": "finance.submit"}])
    svc.submit_txn(db, auth.tenant, t, auth.user.id, body.comment)
    return _txn_out(db, auth, t)


@router.get("/transactions/{txn_id}/receipt.pdf")
def transaction_receipt(txn_id: str, auth: Auth, db: TenantSession) -> Response:
    t = _visible(db, auth, txn_id)
    if t.kind != "INCOME" or t.status != "APPROVED" or t.amount <= 0:
        raise Conflict("Receipts are issued for approved income", code="NO_RECEIPT")
    cat, unit = db.get(FinCategory, t.category_id), db.get(OrgUnit, t.org_unit_id) if t.org_unit_id else None
    fam = db.get(Family, t.family_id) if t.family_id else None
    pdf = receipt_pdf(
        auth.tenant,
        {
            "code": t.code,
            "date": t.txn_date.strftime("%d %b %Y"),
            "payer": t.payer_payee,
            "family": f"{fam.family_name}, {fam.code}" if fam else None,
            "category": cat.name if cat else "",
            "org_unit": unit.name if unit else None,
            "description": t.description,
            "method": t.payment_method.replace("_", " ").title(),
            "reference": t.reference_no,
            "amount": str(t.amount),
            "approved_on": t.approved_at.strftime("%d %b %Y") if t.approved_at else "",
            "approved_by": svc.user_name(db, t.approved_by),
            "generated_by": auth.user.full_name,
        },
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(f"receipt-{t.code}.pdf"),
            "Cache-Control": "no-store",
        },
    )


@router.get("/transactions/{txn_id}/attachments", response_model=list[AttachmentOut])
def txn_files(txn_id: str, auth: Auth, db: TenantSession) -> list[AttachmentOut]:
    t = _visible(db, auth, txn_id)
    return list_attachments(db, auth.tenant, "FIN_TRANSACTION", t.id)


@router.post(
    "/transactions/{txn_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED
)
async def add_txn_file(
    txn_id: str, auth: Auth, db: TenantSession, file: Annotated[UploadFile, File()]
) -> AttachmentOut:
    t = _visible(db, auth, txn_id)
    if not _txn_out(db, auth, t).can_attach:
        raise PermissionDenied("Files cannot be added to this entry")
    return add_attachment(
        db, auth.tenant, "FIN_TRANSACTION", t.id, file.filename or "file", await file.read(), auth.user.id
    )


@router.delete(
    "/transactions/{txn_id}/attachments/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def remove_txn_file(txn_id: str, file_id: str, auth: Auth, db: TenantSession) -> None:
    t = _visible(db, auth, txn_id)
    if not _txn_out(db, auth, t).can_edit:
        raise PermissionDenied("Files can be removed only while the entry is a draft or returned")
    remove_attachment(db, "FIN_TRANSACTION", t.id, file_id, auth.user.id)


# ============================================================================ periods & statements
def _key(key: str) -> tuple[int, int]:
    try:
        y, m = (int(x) for x in key.split("-"))
        date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise ValidationFailed(details=[{"field": "period", "message": "Use YYYY-MM"}]) from exc
    return y, m


def _period_key(p: FinPeriod) -> str:
    return f"{p.year:04d}-{p.month:02d}"


@router.get("/periods", response_model=list[PeriodListOut])
def list_periods(_: PeriodView, db: TenantSession, year: int | None = None) -> list[PeriodListOut]:
    """Months with entries or statements (newest first), plus the current month."""
    today = date.today()
    svc.period_for(db, today)
    stmt = select(FinPeriod).order_by(FinPeriod.year.desc(), FinPeriod.month.desc())
    if year:
        stmt = stmt.where(FinPeriod.year == year)
    out = []
    for p in db.scalars(stmt):
        st = svc.current_statement(db, p)
        snap = (
            st.snapshot
            if st and p.status in ("APPROVED", "RELEASED")
            else svc.build_snapshot(db, p.year, p.month)
        )
        versions = (
            db.scalar(select(func.count()).select_from(FinStatement).where(FinStatement.period_id == p.id))
            or 0
        )
        out.append(
            PeriodListOut(
                key=_period_key(p),
                label=p.label,
                status=p.status,
                income=Decimal(snap["totals"]["income"]),
                expense=Decimal(snap["totals"]["expense"]),
                closing=Decimal(snap["totals"]["closing"]),
                pending=len(snap["pending"]),
                versions=versions,
            )
        )
    return out


def _period(db: Session, key: str) -> FinPeriod:
    y, m = _key(key)
    if date(y, m, 1) > date.today():
        raise NotFound("That month has not started")
    p = svc.period_for(db, date(y, m, 1))
    assert p
    return p


def _period_out(db: Session, auth: Auth, p: FinPeriod) -> PeriodOut:
    stmts = db.scalars(
        select(FinStatement).where(FinStatement.period_id == p.id).order_by(FinStatement.version.desc())
    ).all()
    current = next((s for s in stmts if s.is_current), None)
    live = not (current and p.status in ("APPROVED", "RELEASED"))
    approval = db.scalar(
        select(WorkflowInstance.public_id)
        .where(WorkflowInstance.entity_type == "FIN_PERIOD", WorkflowInstance.entity_id == p.public_id)
        .order_by(WorkflowInstance.id.desc())
        .limit(1)
    )
    perms = auth.permissions
    return PeriodOut(
        id=p.public_id,
        key=_period_key(p),
        label=p.label,
        status=p.status,
        live=live,
        snapshot=svc.build_snapshot(db, p.year, p.month) if live else current.snapshot,  # type: ignore[union-attr]
        statements=[
            StatementVersion(
                id=s.public_id,
                version=s.version,
                generated_at=s.generated_at,
                generated_by=svc.user_name(db, s.generated_by),
                released_at=s.released_at,
                is_current=s.is_current,
                revision_reason=s.revision_reason,
                sha256=s.sha256,
            )
            for s in stmts
        ],
        submitted_at=p.submitted_at,
        approved_at=p.approved_at,
        released_at=p.released_at,
        released_by=svc.user_name(db, p.released_by),
        revision_reason=p.revision_reason,
        approval_id=approval,
        can_close=perms.scope("finance_period.submit").parish_wide
        and p.status == "OPEN"
        and svc.month_bounds(p.year, p.month)[1] < date.today(),
        can_release=perms.scope("finance_period.release").parish_wide and p.status == "APPROVED",
        can_reopen=perms.scope("finance_period.release").parish_wide and p.status == "RELEASED",
    )


@router.get("/periods/{key}", response_model=PeriodOut)
def get_period(key: str, auth: Auth, _: PeriodView, db: TenantSession) -> PeriodOut:
    return _period_out(db, auth, _period(db, key))


@router.post("/periods/{key}/close", response_model=PeriodOut)
def close_period(
    key: str, body: SubmitIn, request: Request, auth: Auth, _: PeriodSubmit, db: TenantSession
) -> PeriodOut:
    p = _period(db, key)
    svc.close_period(db, auth.tenant, p, auth.user.id, body.comment)
    _audit(db, auth, request, "CLOSE", "fin_period", key)
    return _period_out(db, auth, p)


@router.post("/periods/{key}/release", response_model=PeriodOut)
def release_period(key: str, request: Request, auth: Auth, _: PeriodRelease, db: TenantSession) -> PeriodOut:
    p = _period(db, key)
    st = svc.release(db, auth.tenant, p, auth.user.id)
    _audit(
        db, auth, request, "RELEASE", "fin_period", key, remarks=f"statement v{st.version} sha256 {st.sha256}"
    )
    return _period_out(db, auth, p)


@router.post("/periods/{key}/reopen", response_model=PeriodOut)
def reopen_period(
    key: str, body: ReopenIn, request: Request, auth: Auth, _: PeriodRelease, db: TenantSession
) -> PeriodOut:
    p = _period(db, key)
    svc.reopen(db, p, auth.user.id, body.reason)
    _audit(db, auth, request, "REOPEN", "fin_period", key, remarks=body.reason)
    return _period_out(db, auth, p)


@router.get("/statements/{statement_id}/download", response_model=DownloadOut)
def download_statement(
    statement_id: str,
    auth: Auth,
    _: PeriodView,
    db: TenantSession,
    format: Annotated[str, Query(pattern="^(pdf|xlsx)$")] = "pdf",
) -> DownloadOut:
    st = db.scalar(select(FinStatement).where(FinStatement.public_id == statement_id))
    if st is None:
        raise NotFound("Statement not found")
    p = db.get(FinPeriod, st.period_id)
    assert p
    key = st.pdf_key if format == "pdf" else st.xlsx_key
    if not key:
        raise NotFound("File not available")
    filename = f"statement-{_period_key(p)}-v{st.version}.{format}"
    ctype = (
        "application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    url = get_storage().download_url(
        key, filename=filename, content_type=ctype, tenant_public_id=auth.tenant.public_id
    )
    return DownloadOut(url=url, filename=filename)


# ============================================================================ summary
@router.get("/summary", response_model=SummaryOut)
def summary(
    auth: Auth,
    db: TenantSession,
    _: Annotated[list[PermissionScope], Depends(require_any("finance.view_summary", "finance.view"))],
) -> SummaryOut:
    """Totals for the dashboard: this month and the financial year to date, within the user's scope."""
    from app.modules.parish.models import ParishProfile

    perms = auth.permissions
    scope = (
        perms.scope("finance.view")
        if perms.scope("finance.view").granted
        else perms.scope("finance.view_summary")
    )
    today = date.today()
    prof = db.get(ParishProfile, 1)
    fy_month = prof.fy_start_month if prof else 4
    fy_year = today.year if today.month >= fy_month else today.year - 1
    fy_start = date(fy_year, fy_month, 1)
    month_start = today.replace(day=1)
    base = (
        select(FinTransaction.kind, func.coalesce(func.sum(FinTransaction.amount), 0))
        .where(
            FinTransaction.status == "APPROVED",
            FinTransaction.is_deleted.is_(False),
            FinTransaction.kind.in_(("INCOME", "EXPENSE")),
            scope.filter(FinTransaction.org_unit_id),
        )
        .group_by(FinTransaction.kind)
    )

    def sums(start: date) -> dict[str, Decimal]:
        return {
            k: svc.money(v)
            for k, v in db.execute(
                base.where(FinTransaction.txn_date >= start, FinTransaction.txn_date <= today)
            ).all()
        }

    month, fy = sums(month_start), sums(fy_start)
    pending = (
        db.scalar(
            select(func.count())
            .select_from(FinTransaction)
            .where(
                FinTransaction.status == "IN_REVIEW",
                FinTransaction.is_deleted.is_(False),
                scope.filter(FinTransaction.org_unit_id),
            )
        )
        or 0
    )
    balance = None
    view = perms.scope("finance.view")
    if view.granted:
        accounts = db.scalars(
            select(FinAccount).where(FinAccount.is_deleted.is_(False), view.filter(FinAccount.org_unit_id))
        ).all()
        bal = svc.balances(db, today, {a.id for a in accounts})
        balance = svc.money(sum(bal.values(), Decimal(0)))
    released = db.scalar(
        select(FinPeriod)
        .where(FinPeriod.status == "RELEASED")
        .order_by(FinPeriod.year.desc(), FinPeriod.month.desc())
        .limit(1)
    )
    return SummaryOut(
        month=month_start.strftime("%B %Y"),
        income=month.get("INCOME", svc.ZERO),
        expense=month.get("EXPENSE", svc.ZERO),
        fy_label=f"FY {fy_year}–{str(fy_year + 1)[-2:]}" if fy_month != 1 else f"FY {fy_year}",
        fy_income=fy.get("INCOME", svc.ZERO),
        fy_expense=fy.get("EXPENSE", svc.ZERO),
        pending_entries=pending,
        balance=balance,
        last_released=released.label if released else None,
    )

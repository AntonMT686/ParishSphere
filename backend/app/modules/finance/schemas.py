from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

Money = Decimal


class FinRef(BaseModel):
    id: str
    name: str


class AccountIn(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=150)
    kind: Literal["CASH", "BANK", "DIGITAL"]
    org_unit_id: str | None = Field(default=None, max_length=26)
    bank_name: str | None = Field(default=None, max_length=150)
    account_number_masked: str | None = Field(default=None, max_length=30, description="e.g. XXXX1234")
    opening_balance: Money = Field(default=Decimal("0"), max_digits=14, decimal_places=2)
    opening_date: date


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    bank_name: str | None = Field(default=None, max_length=150)
    account_number_masked: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None


class AccountOut(BaseModel):
    id: str
    code: str
    name: str
    kind: str
    org_unit: FinRef | None
    bank_name: str | None
    account_number_masked: str | None
    opening_balance: Money
    opening_date: date
    is_active: bool
    balance: Money | None = Field(description="Approved balance today")
    pending: int


class CategoryIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=150)
    name_local: str | None = Field(default=None, max_length=150)
    kind: Literal["INCOME", "EXPENSE"]
    sort_order: int = Field(default=100, ge=0, le=10000)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    name_local: str | None = Field(default=None, max_length=150)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class CategoryOut(BaseModel):
    id: str
    code: str
    name: str
    name_local: str | None
    kind: str
    sort_order: int
    is_active: bool
    is_system: bool


class TxnIn(BaseModel):
    txn_date: date
    kind: Literal["INCOME", "EXPENSE", "TRANSFER"]
    org_unit_id: str | None = Field(default=None, max_length=26)
    category_id: str | None = Field(default=None, max_length=26)
    account_id: str = Field(max_length=26)
    to_account_id: str | None = Field(default=None, max_length=26)
    amount: Money = Field(max_digits=14, decimal_places=2)
    payment_method: Literal["CASH", "CHEQUE", "BANK_TRANSFER", "UPI", "CARD", "ONLINE"] = "CASH"
    reference_no: str | None = Field(default=None, max_length=100)
    description: str = Field(min_length=2, max_length=2000)
    payer_payee: str | None = Field(default=None, max_length=200)
    family_id: str | None = Field(default=None, max_length=26)
    adjusts_transaction_id: str | None = Field(
        default=None, max_length=26, description="Entry being corrected"
    )


class TxnListOut(BaseModel):
    id: str
    code: str
    txn_date: date
    kind: str
    category: FinRef | None
    account: FinRef
    to_account: FinRef | None
    org_unit: FinRef | None
    amount: Money
    payment_method: str
    description: str
    payer_payee: str | None
    status: str
    is_correction: bool


class TxnOut(TxnListOut):
    reference_no: str | None
    family: FinRef | None
    period: str
    period_status: str
    adjusts: FinRef | None
    corrections: list[FinRef]
    entered_by: str | None
    reviewed_by: str | None
    approved_by: str | None
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    approval_id: str | None
    can_edit: bool
    can_submit: bool
    can_delete: bool
    can_correct: bool
    can_attach: bool


class SubmitIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class ReopenIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class StatementVersion(BaseModel):
    id: str
    version: int
    generated_at: datetime
    generated_by: str | None
    released_at: datetime | None
    is_current: bool
    revision_reason: str | None
    sha256: str


class PeriodListOut(BaseModel):
    key: str = Field(description="YYYY-MM")
    label: str
    status: str
    income: Money
    expense: Money
    closing: Money | None
    pending: int
    versions: int


class PeriodOut(BaseModel):
    id: str
    key: str
    label: str
    status: str
    live: bool = Field(description="True: figures computed now; False: from the generated statement")
    snapshot: dict[str, Any]
    statements: list[StatementVersion]
    submitted_at: datetime | None
    approved_at: datetime | None
    released_at: datetime | None
    released_by: str | None
    revision_reason: str | None
    approval_id: str | None
    can_close: bool
    can_release: bool
    can_reopen: bool


class DownloadOut(BaseModel):
    url: str
    filename: str


class SummaryOut(BaseModel):
    month: str
    income: Money
    expense: Money
    fy_label: str
    fy_income: Money
    fy_expense: Money
    pending_entries: int
    balance: Money | None = Field(description="Total approved balance of the accounts you can see")
    last_released: str | None

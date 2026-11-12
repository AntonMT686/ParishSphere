"""One ledger for all money of the parish and its organisations, with monthly periods and statements."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow

MONEY = Numeric(14, 2)


class FinAccount(StandardMixin, TenantBase):
    """A cash box, bank account or digital wallet, held by the parish or by one organisation."""

    __tablename__ = "fin_accounts"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # CASH, BANK, DIGITAL
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    bank_name: Mapped[str | None] = mapped_column(String(150))
    account_number_masked: Mapped[str | None] = mapped_column(String(30))
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    opening_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FinCategory(StandardMixin, TenantBase):
    __tablename__ = "fin_categories"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # INCOME, EXPENSE
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FinPeriod(IdMixin, PublicIdMixin, TenantBase):
    """A calendar month. OPEN → UNDER_REVIEW → APPROVED (statement generated) → RELEASED (locked)."""

    __tablename__ = "fin_periods"
    __table_args__ = (UniqueConstraint("year", "month"),)

    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="OPEN", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime())
    submitted_by: Mapped[int | None] = mapped_column(BigIntPK)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime())
    released_at: Mapped[datetime | None] = mapped_column(DateTime())
    released_by: Mapped[int | None] = mapped_column(BigIntPK)
    # Set when a released month is reopened; becomes the next statement version's revision reason.
    revision_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    @property
    def label(self) -> str:
        return date(self.year, self.month, 1).strftime("%B %Y")

    @property
    def is_open(self) -> bool:
        return self.status == "OPEN"


class FinTransaction(StandardMixin, TenantBase):
    __tablename__ = "fin_transactions"
    __table_args__ = (CheckConstraint("amount <> 0", name="amount_not_zero"),)

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    txn_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # INCOME, EXPENSE, TRANSFER
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("fin_categories.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("fin_accounts.id"), nullable=False, index=True)
    to_account_id: Mapped[int | None] = mapped_column(ForeignKey("fin_accounts.id"))
    # Positive; negative only for corrections of an earlier entry (adjusts_transaction_id set).
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(15), nullable=False, default="CASH")
    reference_no: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    payer_payee: Mapped[str | None] = mapped_column(String(200))
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("fin_periods.id"), nullable=False, index=True)
    # DRAFT, IN_REVIEW, REWORK, APPROVED, REJECTED, VOID
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="DRAFT", index=True)
    adjusts_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("fin_transactions.id"))
    source: Mapped[str] = mapped_column(String(15), nullable=False, default="MANUAL")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime())
    reviewed_by: Mapped[int | None] = mapped_column(BigIntPK)
    approved_by: Mapped[int | None] = mapped_column(BigIntPK)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime())

    def effect(self, account_id: int) -> Decimal:
        """Signed effect of this entry on ``account_id`` (only meaningful once approved)."""
        if self.kind == "INCOME":
            return self.amount if self.account_id == account_id else Decimal(0)
        if self.kind == "EXPENSE":
            return -self.amount if self.account_id == account_id else Decimal(0)
        out = Decimal(0)
        if self.account_id == account_id:
            out -= self.amount
        if self.to_account_id == account_id:
            out += self.amount
        return out


class FinStatement(IdMixin, PublicIdMixin, TenantBase):
    """An immutable, versioned monthly statement (snapshot + PDF + XLSX)."""

    __tablename__ = "fin_statements"
    __table_args__ = (UniqueConstraint("period_id", "version"),)

    period_id: Mapped[int] = mapped_column(ForeignKey("fin_periods.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pdf_key: Mapped[str | None] = mapped_column(String(255))
    xlsx_key: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    generated_by: Mapped[int | None] = mapped_column(BigIntPK)
    released_at: Mapped[datetime | None] = mapped_column(DateTime())
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revision_reason: Mapped[str | None] = mapped_column(String(500))

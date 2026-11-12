# 17 — Finance & Monthly Statements (T12)

One ledger for the parish and every organisation. Donations, offerings, society expenses and Anbiyam contributions are all entries in `fin_transactions`, tagged with the organisation. Monthly statements are built from that ledger, approved, released and locked.

## Accounts and categories

**Accounts** (`fin_accounts`) are of three kinds:
- Cash, bank, or digital (UPI / wallet).
- Each is held by the parish, or by one organisation (for example the Youth Society's cash box).
- Each has an opening balance and opening date. Entries before the opening date are rejected.
- An account can't be switched off while it has undecided entries.

**Categories** (`fin_categories`) are seeded from the brief:
- **Income:** Donations, Offerings / Sunday collection, Membership contributions, Festival collections, Special contributions, Other income.
- **Expenses:** Church maintenance, Festival expenses, Charity, Administrative, Society expenses, Anbiyam expenses, Other expenses.
- Each category has a Tamil name.

The parish can add, rename and switch off categories. That requires the new permission `finance.configure` (Parish Treasurer and Parish Priest by default; existing parishes receive it on migration).

## Entries

`fin_transactions` (`TXN-2026-000045`).

**Kinds:**
- **Income:** category, account, received from, optional family link (donations).
- **Expense:** category, account, paid to.
- **Transfer:** from one account to another; no category, and not counted as income or expense.

**Every entry has:** date, organisation, amount, mode (cash, cheque, bank transfer, UPI, card, online), reference no., particulars, supporting documents.

**Audit trail:** who entered, reviewed and approved it, and when.

**Lifecycle:**

```
DRAFT ──submit──▶ IN_REVIEW ──(FIN_TRANSACTION workflow)──▶ APPROVED
  ▲                   └─return─▶ REWORK ─resubmit─▶ IN_REVIEW        └─reject─▶ REJECTED
  └─withdraw                                         DRAFT ──delete──▶ VOID
```

**Approval routing:**
- The workflow context carries the amount and category code, so parishes can route by both.
- **Default:** Parish Treasurer → Parish Priest.
- **₹50,000 or more:** Parish Treasurer → Parish President **and** Parish Secretary → Parish Priest.
- When the treasurer submits their own entry, their stage is skipped automatically.

**Validation:**
- dates can't be in the future or before the account opened;
- the category must match the kind;
- a transfer needs two different active accounts;
- an organisation's account can only carry that organisation's entries;
- parish accounts can be used only with a parish-wide `finance.create`;
- amounts must be positive.

**Corrections:**
- An approved entry is never edited. "Correct this entry" creates a new entry that references it (`adjusts_transaction_id`).
- A correction may be negative, for example −₹500 to reduce an overstated offering.
- Corrections are approved like any other entry.

**Receipts:** `GET /finance/transactions/{id}/receipt.pdf` produces a receipt for approved income.

## Accounting rules

1. **Only approved entries count.** They affect balances, statements and summaries.
2. **Each entry belongs to the month of its date.** In a month that is not `OPEN`, nothing can be entered, edited, submitted, approved or deleted. An approval that arrives after its month was closed is refused.
3. **Closing a month** requires:
   - the month has ended;
   - no entry of that month is undecided (draft, under review or returned);
   - every earlier month that has entries is closed.
4. **Balance arithmetic.** An account's balance is its opening balance plus approved income, minus approved expenses, plus or minus transfers. Statements recompute this from entries, so a released version can never drift.

## Monthly periods & statements

```
OPEN ──close (Treasurer)──▶ UNDER_REVIEW ──approve (FIN_PERIOD workflow, Priest)──▶ APPROVED ──release (Priest)──▶ RELEASED
  ▲                               └─return / reject──▶ OPEN                                                       │
  └────────────────────────────── reopen with a reason (Priest; latest released month only) ◀────────────────────┘
```

**On approval** the statement is generated and stored as an immutable version (`fin_statements`):
- a **snapshot**, with these sections:
  - opening / income / expense / surplus / closing totals;
  - per-account opening, income, expense, transfers and closing;
  - income and expenditure by category;
  - totals by organisation;
  - pending entries.
- a **PDF** (with signature lines) and an **Excel workbook** (Summary, Categories, Organisations), kept in storage;
- the **SHA-256** of the PDF.

**On release:**
- the month stays locked;
- the version is stamped as released;
- holders of `finance_period.view` / `finance.view_summary` are notified (`statement.released`).

**Corrections after release:**
- The Parish Priest reopens the latest released month, with a mandatory reason. Earlier months can't be reopened once a later one is closed.
- The treasurer enters corrections and closes the month again.
- Approval generates **version 2**, which carries the revision reason. Version 1 stays stored, downloadable and marked released.

## Summary

`GET /finance/summary` provides, within the user's scope:
- income and expenditure for this month and the financial year to date (using the start month from Parish Settings);
- entries awaiting approval;
- the total approved balance, for users with `finance.view`;
- the last released month.

It feeds the dashboard card and the cards on the Transactions page.

## Who sees what

| Permission | Gives |
|---|---|
| `finance.view` (scoped) | Entries and balances of the user's organisations; parish-wide holders see everything |
| `finance.create` / `update` / `delete` / `submit` | Enter, edit, delete drafts and submit, for the user's organisations (entries they entered stay visible to them) |
| `finance.export` | CSV / Excel / PDF export of entries |
| `finance.configure` (parish-wide) | Accounts and categories |
| `finance.view_summary` | Dashboard totals only |
| `finance_period.view` / `submit` / `release` (parish-wide) | Statements; close a month; release and reopen |

Reviews and approvals of entries and months follow the configured workflows (T10), not these permissions.

## API

| Endpoint | Purpose |
|---|---|
| `GET/POST /finance/accounts`, `PATCH /finance/accounts/{id}` | accounts with balances |
| `GET/POST /finance/categories`, `PATCH /finance/categories/{id}` | categories |
| `GET /finance/transactions[?q&kind&status=PENDING|…&category&account&org_unit&period=YYYY-MM&date_from&date_to]` | ledger |
| `POST /finance/transactions`, `GET/PUT/DELETE /finance/transactions/{id}`, `POST …/submit`, `GET …/receipt.pdf`, attachments | entries |
| `GET /finance/transactions/export?format=csv|xlsx|pdf` | export |
| `GET /finance/periods`, `GET /finance/periods/{YYYY-MM}` | months: live figures, or the generated statement and its versions |
| `POST /finance/periods/{YYYY-MM}/close`, `/release`, `/reopen` | month lifecycle |
| `GET /finance/statements/{id}/download?format=pdf|xlsx` | signed download link |
| `GET /finance/summary` | dashboard totals |

## Screens

- **Finance → Transactions:**
  - summary cards; filters (type, status, category, organisation, account, dates); export;
  - **New entry**, where the organisation and account pickers only offer what the user may use.
  - The entry page shows the audit trail, links to corrections, receipt, supporting documents, and the approval timeline with the decision panel.
- **Finance → Monthly Statements:**
  - the list of months;
  - the statement page: live figures while open; the version on file once approved. It has the accounts table, category and organisation breakdowns, pending entries, statement versions with PDF/Excel downloads and checksums, and Close / Release / Reopen.
- **Finance → Accounts:** accounts with balances and pending counts, and a categories tab.
- **Dashboard:** finance card.

## Upgrading

```bash
ps-admin migrate-tenants
```

Tenant migration `0010` creates the five finance tables. The seeder adds the categories and a *Parish cash* account, and `finance.configure` is granted to the Parish Treasurer and Parish Priest. Open **Finance → Accounts** to add bank accounts and organisations' cash boxes, with their opening balances.

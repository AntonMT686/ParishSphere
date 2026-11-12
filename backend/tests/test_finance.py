"""Finance: accounts, categories, transactions with approval, periods and statements (T12)."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.ratelimit import counter
from app.common.storage import reset_storage
from app.core.config import get_settings
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.finance.models import FinAccount, FinCategory, FinStatement
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.notifications.models import Notification
from app.modules.org_units.models import OrgUnit
from app.modules.rbac.service import assign_role, role_by_code
from tests.conftest import auth, make_org_unit

HOST = {"Host": "fin.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)
TODAY = date.today()
LAST = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)  # first day of last month
BEFORE = (LAST - timedelta(days=1)).replace(day=1)  # first day of the month before


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="FIN", name="St. Thomas Church"))
        s.commit()
    return provision_parish("FIN")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # type: ignore[no-untyped-def]
    counter().reset()
    monkeypatch.setattr(get_settings(), "storage_local_dir", tmp_path / "files")
    reset_storage()
    yield
    reset_storage()


def make_user(tenant: TenantDescriptor, *roles: str, unit: int | None = None) -> User:
    username = f"f{next(_n)}"
    with tenant_session_scope(tenant) as s:
        u = create_user(
            s, username=username, full_name=f"Person {username}", password=PW, must_change_password=False
        )
        for code in roles:
            r = role_by_code(s, code)
            assert r
            assign_role(s, u, r, org_unit_id=unit)
        s.flush()
        s.expunge(u)
    return u


def login(client: TestClient, user: User) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": user.username, "password": PW}, headers=HOST)
    assert r.status_code == 200, r.text
    return {**HOST, **auth(r.json()["access_token"])}


@pytest.fixture(scope="module")
def people(tenant: TenantDescriptor) -> dict[str, User]:
    return {
        "treasurer": make_user(tenant, "PARISH_TREASURER"),
        "priest": make_user(tenant, "PARISH_PRIEST"),
        "secretary": make_user(tenant, "PARISH_SECRETARY"),
        "president": make_user(tenant, "PARISH_PRESIDENT"),
    }


def cat(tenant: TenantDescriptor, code: str) -> str:
    with tenant_session_scope(tenant) as s:
        c = s.scalar(select(FinCategory).where(FinCategory.code == code))
        assert c
        return c.public_id


def account(
    client: TestClient,
    h: dict[str, str],
    code: str,
    kind: str = "CASH",
    unit: str | None = None,
    opening: str = "1000.00",
    on: date | None = None,
) -> str:
    r = client.post(
        "/api/v1/finance/accounts",
        json={
            "code": code,
            "name": f"{code} account",
            "kind": kind,
            "org_unit_id": unit,
            "opening_balance": opening,
            "opening_date": str(on or BEFORE - timedelta(days=60)),
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]  # type: ignore[no-any-return]


def entry(
    client: TestClient,
    h: dict[str, str],
    acc: str,
    category: str | None,
    amount: str,
    kind: str = "INCOME",
    on: date = TODAY,
    **kw: object,
) -> dict:
    body = {
        "txn_date": str(on),
        "kind": kind,
        "category_id": category,
        "account_id": acc,
        "amount": amount,
        "description": kw.pop("description", "Sunday collection"),
        **kw,
    }
    r = client.post("/api/v1/finance/transactions", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def approve_all(client: TestClient, *users: User) -> None:
    """Each user approves everything waiting for them."""
    for u in users:
        h = login(client, u)
        for t in client.get("/api/v1/workflow/tasks?size=100", headers=h).json()["items"]:
            r = client.post(f"/api/v1/workflow/tasks/{t['id']}/act", json={"action": "APPROVE"}, headers=h)
            assert r.status_code == 200, r.text


def balance(client: TestClient, h: dict[str, str], acc: str) -> str:
    rows = {a["id"]: a for a in client.get("/api/v1/finance/accounts", headers=h).json()}
    return rows[acc]["balance"]  # type: ignore[no-any-return]


# ============================================================================ setup
def test_seeded_categories_and_configuration(
    client: TestClient, tenant: TenantDescriptor, people: dict
) -> None:
    h = login(client, people["treasurer"])
    cats = client.get("/api/v1/finance/categories", headers=h).json()
    codes = {c["code"] for c in cats}
    assert {
        "DONATION",
        "OFFERING",
        "FESTIVAL_COLLECTION",
        "MAINTENANCE",
        "CHARITY",
        "ANBIYAM_EXPENSE",
    } <= codes
    assert len([c for c in cats if c["kind"] == "INCOME"]) == 6
    assert [a["code"] for a in client.get("/api/v1/finance/accounts", headers=h).json()] == ["CASH"]
    r = client.post(
        "/api/v1/finance/categories",
        json={"code": "BUILDING_FUND", "name": "Building fund", "kind": "INCOME"},
        headers=h,
    )
    assert r.status_code == 201
    unit = make_org_unit(tenant, "SOCIETY")
    society_treasurer = login(client, make_user(tenant, "COMMITTEE_TREASURER", unit=unit))
    assert (
        client.post(
            "/api/v1/finance/categories",
            json={"code": "X_Y", "name": "Nope", "kind": "INCOME"},
            headers=society_treasurer,
        ).status_code
        == 403
    )


# ============================================================================ transactions
def test_entry_validation(client: TestClient, tenant: TenantDescriptor, people: dict) -> None:
    h = login(client, people["treasurer"])
    acc = account(client, h, "VAL")
    bank = account(client, h, "VALBANK", "BANK")
    bad = [
        ({"category_id": cat(tenant, "MAINTENANCE")}, "category_id"),  # expense category on income
        ({"txn_date": str(TODAY + timedelta(days=1))}, "txn_date"),
        ({"txn_date": str(BEFORE - timedelta(days=400))}, "txn_date"),  # before the account opened
        ({"amount": "-50.00"}, "amount"),  # negative only for corrections
        ({"kind": "TRANSFER", "category_id": None, "to_account_id": acc}, "to_account_id"),  # same account
    ]
    for patch, field in bad:
        body = {
            "txn_date": str(TODAY),
            "kind": "INCOME",
            "category_id": cat(tenant, "OFFERING"),
            "account_id": acc,
            "amount": "100.00",
            "description": "Test",
            **patch,
        }
        r = client.post("/api/v1/finance/transactions", json=body, headers=h)
        assert r.status_code == 422, (patch, r.text)
        assert r.json()["error"]["details"][0]["field"] == field
    t = entry(
        client, h, acc, None, "250.00", kind="TRANSFER", to_account_id=bank, description="Deposit to bank"
    )
    assert t["status"] == "DRAFT" and t["code"].startswith(f"TXN-{TODAY.year}-") and t["category"] is None


def test_approval_balances_scope_and_receipt(
    client: TestClient, tenant: TenantDescriptor, people: dict
) -> None:
    th = login(client, people["treasurer"])
    unit = make_org_unit(tenant, "SOCIETY", "Youth Society")
    with tenant_session_scope(tenant) as s:
        upid = s.get(OrgUnit, unit).public_id  # type: ignore[union-attr]
    soc_acc = account(client, th, "YOUTHCASH", unit=upid, opening="500.00")
    st = make_user(tenant, "COMMITTEE_TREASURER", unit=unit)
    sh = login(client, st)
    # The society treasurer only sees the society's account and cannot post to the parish cash box.
    assert [a["id"] for a in client.get("/api/v1/finance/accounts", headers=sh).json()] == [soc_acc]
    parish_cash = next(
        a["id"] for a in client.get("/api/v1/finance/accounts", headers=th).json() if a["code"] == "CASH"
    )
    r = client.post(
        "/api/v1/finance/transactions",
        json={
            "txn_date": str(TODAY),
            "kind": "EXPENSE",
            "category_id": cat(tenant, "SOCIETY_EXPENSE"),
            "account_id": parish_cash,
            "amount": "10",
            "description": "Snacks",
            "org_unit_id": upid,
        },
        headers=sh,
    )
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "account_id"
    t = entry(
        client,
        sh,
        soc_acc,
        cat(tenant, "SOCIETY_EXPENSE"),
        "180.00",
        kind="EXPENSE",
        org_unit_id=upid,
        description="Snacks for the youth meet",
        payer_payee="Bakery",
    )
    assert (
        client.post(f"/api/v1/finance/transactions/{t['id']}/submit", json={}, headers=sh).json()["status"]
        == "IN_REVIEW"
    )
    assert balance(client, th, soc_acc) == "500.00"  # nothing changes until approved
    r = client.put(
        f"/api/v1/finance/transactions/{t['id']}",
        json={
            "txn_date": str(TODAY),
            "kind": "EXPENSE",
            "category_id": cat(tenant, "SOCIETY_EXPENSE"),
            "account_id": soc_acc,
            "amount": "1",
            "description": "Snacks",
            "org_unit_id": upid,
        },
        headers=sh,
    )
    assert r.status_code == 409
    approve_all(client, people["treasurer"], people["priest"])  # Parish Treasurer → Parish Priest
    got = client.get(f"/api/v1/finance/transactions/{t['id']}", headers=sh).json()
    assert got["status"] == "APPROVED" and got["approved_by"] == people["priest"].full_name
    assert got["reviewed_by"] == people["treasurer"].full_name
    assert balance(client, th, soc_acc) == "320.00"
    # Another society's treasurer cannot see it.
    other = login(client, make_user(tenant, "COMMITTEE_TREASURER", unit=make_org_unit(tenant, "SOCIETY")))
    assert client.get(f"/api/v1/finance/transactions/{t['id']}", headers=other).status_code == 404
    # Income receipt
    inc = entry(client, th, parish_cash, cat(tenant, "DONATION"), "5000.00", payer_payee="Rayappan family")
    client.post(f"/api/v1/finance/transactions/{inc['id']}/submit", json={}, headers=th)
    approve_all(client, people["priest"])
    r = client.get(f"/api/v1/finance/transactions/{inc['id']}/receipt.pdf", headers=th)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert client.get(f"/api/v1/finance/transactions/{t['id']}/receipt.pdf", headers=th).status_code == 409
    s = client.get("/api/v1/finance/summary", headers=th).json()
    assert float(s["income"]) >= 5000 and float(s["expense"]) >= 180
    ssum = client.get("/api/v1/finance/summary", headers=sh).json()
    assert ssum["income"] == "0.00" and ssum["expense"] == "180.00"  # scoped to the society


def test_large_expense_needs_both_council_officers(
    client: TestClient, tenant: TenantDescriptor, people: dict
) -> None:
    th = login(client, people["treasurer"])
    cash = next(
        a["id"] for a in client.get("/api/v1/finance/accounts", headers=th).json() if a["code"] == "CASH"
    )
    t = entry(
        client, th, cash, cat(tenant, "MAINTENANCE"), "60000.00", kind="EXPENSE", description="Roof repair"
    )
    inst = client.post(f"/api/v1/finance/transactions/{t['id']}/submit", json={}, headers=th).json()[
        "approval_id"
    ]
    d = client.get(f"/api/v1/workflow/instances/{inst}", headers=th).json()
    assert d["definition"]["code"] == "FIN_TXN_LARGE"
    # The treasurer submitted, so the treasurer stage is skipped; both officers must approve.
    assert d["stages"][0]["state"] == "SKIPPED"
    assert set(d["pending_with"]) == {people["president"].full_name, people["secretary"].full_name}
    approve_all(client, people["president"])
    assert client.get(f"/api/v1/finance/transactions/{t['id']}", headers=th).json()["status"] == "IN_REVIEW"
    approve_all(client, people["secretary"], people["priest"])
    assert client.get(f"/api/v1/finance/transactions/{t['id']}", headers=th).json()["status"] == "APPROVED"


# ============================================================================ periods & statements
def test_month_close_approve_release_reopen_revise(
    client: TestClient, tenant: TenantDescriptor, people: dict
) -> None:
    th, ph = login(client, people["treasurer"]), login(client, people["priest"])
    acc = account(client, th, "STMT", opening="10000.00")
    old = entry(client, th, acc, cat(tenant, "OFFERING"), "1200.00", on=BEFORE + timedelta(days=4))
    t1 = entry(client, th, acc, cat(tenant, "OFFERING"), "2500.00", on=LAST + timedelta(days=2))
    t2 = entry(client, th, acc, cat(tenant, "CHARITY"), "800.00", kind="EXPENSE", on=LAST + timedelta(days=9))
    key_last, key_before = f"{LAST:%Y-%m}", f"{BEFORE:%Y-%m}"
    # Not yet: entries undecided, earlier month open, current month not ended.
    r = client.post(f"/api/v1/finance/periods/{key_before}/close", json={}, headers=th)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PENDING_ENTRIES"
    assert (
        client.post(f"/api/v1/finance/periods/{TODAY:%Y-%m}/close", json={}, headers=th).json()["error"][
            "code"
        ]
        == "PERIOD_NOT_ENDED"
    )
    for t in (old, t1, t2):
        client.post(f"/api/v1/finance/transactions/{t['id']}/submit", json={}, headers=th)
    approve_all(client, people["priest"])
    r = client.post(f"/api/v1/finance/periods/{key_last}/close", json={}, headers=th)
    assert r.status_code == 409 and r.json()["error"]["code"] == "EARLIER_PERIOD_OPEN"
    for key in (key_before, key_last):
        r = client.post(
            f"/api/v1/finance/periods/{key}/close", json={"comment": "All entries checked"}, headers=th
        )
        assert r.status_code == 200 and r.json()["status"] == "UNDER_REVIEW", r.text
    # A month under review is locked.
    r = client.post(
        "/api/v1/finance/transactions",
        json={
            "txn_date": str(LAST + timedelta(days=3)),
            "kind": "INCOME",
            "category_id": cat(tenant, "OFFERING"),
            "account_id": acc,
            "amount": "5",
            "description": "late",
        },
        headers=th,
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "PERIOD_CLOSED", r.text
    approve_all(client, people["priest"])  # Parish Priest approves both statements
    p = client.get(f"/api/v1/finance/periods/{key_last}", headers=ph).json()
    assert p["status"] == "APPROVED" and p["live"] is False and p["can_release"]
    s = p["snapshot"]
    row = next(a for a in s["accounts"] if a["code"] == "STMT")
    assert (row["opening"], row["income"], row["expense"], row["closing"]) == (
        "11200.00",
        "2500.00",
        "800.00",
        "12900.00",
    )
    assert {c["code"]: c["amount"] for c in s["income_by_category"]}["OFFERING"] == "2500.00"
    assert s["pending"] == [] and p["statements"][0]["version"] == 1
    # Files: PDF and a real workbook.
    for fmt in ("pdf", "xlsx"):
        dl = client.get(
            f"/api/v1/finance/statements/{p['statements'][0]['id']}/download?format={fmt}", headers=ph
        ).json()
        body = client.get(dl["url"], headers=HOST).content
        if fmt == "pdf":
            assert body.startswith(b"%PDF")
        else:
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(body))
            assert wb.sheetnames == ["Summary", "Categories", "Organisations"]
    # Release (priest only) → locked, everyone with statement access notified.
    assert client.post(f"/api/v1/finance/periods/{key_last}/release", headers=th).status_code == 403
    r = client.post(f"/api/v1/finance/periods/{key_last}/release", headers=ph)
    assert r.json()["status"] == "RELEASED" and r.json()["statements"][0]["released_at"]
    with tenant_session_scope(tenant) as db:
        assert db.scalar(
            select(Notification).where(
                Notification.user_id == people["treasurer"].id,
                Notification.event_code == "statement.released",
            )
        )
    # Reopen the latest released month to correct an entry → version 2 with the reason; v1 kept.
    assert client.post(f"/api/v1/finance/periods/{key_before}/release", headers=ph).status_code == 200
    r = client.post(
        f"/api/v1/finance/periods/{key_before}/reopen", json={"reason": "Typo in an entry"}, headers=ph
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "LATER_PERIOD_CLOSED", r.text
    r = client.post(
        f"/api/v1/finance/periods/{key_last}/reopen",
        json={"reason": "Offering was ₹2,000, not ₹2,500"},
        headers=ph,
    )
    assert r.json()["status"] == "OPEN"
    fix = entry(
        client,
        th,
        acc,
        cat(tenant, "OFFERING"),
        "-500.00",
        on=LAST + timedelta(days=2),
        adjusts_transaction_id=t1["id"],
        description="Correction of the 2nd-week offering",
    )
    assert fix["is_correction"] is True
    client.post(f"/api/v1/finance/transactions/{fix['id']}/submit", json={}, headers=th)
    approve_all(client, people["priest"])
    client.post(f"/api/v1/finance/periods/{key_last}/close", json={}, headers=th)
    approve_all(client, people["priest"])
    p = client.get(f"/api/v1/finance/periods/{key_last}", headers=ph).json()
    assert [v["version"] for v in p["statements"]] == [2, 1] and p["statements"][1]["is_current"] is False
    assert p["statements"][0]["revision_reason"].startswith("Offering was")
    assert next(a for a in p["snapshot"]["accounts"] if a["code"] == "STMT")["closing"] == "12400.00"
    with tenant_session_scope(tenant) as db:
        v1 = db.scalar(
            select(FinStatement).where(
                FinStatement.version == 1, FinStatement.public_id == r.json()["statements"][0]["id"]
            )
        )
        assert v1 is not None and v1.released_at is not None  # the released version is preserved
    listed = {p_["key"]: p_ for p_ in client.get("/api/v1/finance/periods", headers=ph).json()}
    assert listed[key_last]["versions"] == 2 and listed[key_before]["status"] == "RELEASED"
    # Statements are parish-level: a society treasurer has no access.
    sh = login(client, make_user(tenant, "COMMITTEE_TREASURER", unit=make_org_unit(tenant, "SOCIETY")))
    assert client.get(f"/api/v1/finance/periods/{key_last}", headers=sh).status_code == 403


def test_accounts_cannot_be_closed_with_pending_entries(
    client: TestClient, tenant: TenantDescriptor, people: dict
) -> None:
    th = login(client, people["treasurer"])
    acc = account(client, th, "PEND")
    entry(client, th, acc, cat(tenant, "OFFERING"), "10.00")
    r = client.patch(f"/api/v1/finance/accounts/{acc}", json={"is_active": False}, headers=th)
    assert r.status_code == 409
    with tenant_session_scope(tenant) as db:
        assert db.scalar(select(FinAccount).where(FinAccount.public_id == acc)).is_active  # type: ignore[union-attr]

"""Role dashboards (T14): permission-driven sections, scoped figures."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.ratelimit import counter
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.finance.models import FinCategory
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.org_units.models import OrgUnit
from app.modules.people.models import Member
from app.modules.rbac.service import assign_role, role_by_code
from tests.conftest import auth, make_org_unit

HOST = {"Host": "dsh.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
TODAY = date.today()
_n = count(1)
_phone = count(9840000001)


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="DSH", name="St. Joseph's Church"))
        s.commit()
    return provision_parish("DSH")


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    counter().reset()
    yield


def make_user(tenant: TenantDescriptor, *roles: str, unit: int | None = None) -> User:
    username = f"d{next(_n)}"
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


def pid(tenant: TenantDescriptor, unit: int) -> str:
    with tenant_session_scope(tenant) as s:
        return s.get(OrgUnit, unit).public_id  # type: ignore[union-attr]


def yrs(age: int) -> str:
    return str(TODAY.replace(year=TODAY.year - age) - timedelta(days=10))


def register(client: TestClient, h: dict[str, str], name: str, anbiyam: str | None, members: list) -> dict:
    body = {
        "family_name": name,
        "phone": f"+91 {next(_phone)}",
        "address_line1": "1 Church Street",
        "city": "Chennai",
        "anbiyam_id": anbiyam,
        "members": [
            {"first_name": f, "gender": g, "relationship_to_head": rel, "date_of_birth": yrs(a)}
            for f, g, rel, a in members
        ],
    }
    r = client.post("/api/v1/families", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def approve_all(client: TestClient, *users: User) -> None:
    for u in users:
        h = login(client, u)
        for t in client.get("/api/v1/workflow/tasks?size=100", headers=h).json()["items"]:
            r = client.post(f"/api/v1/workflow/tasks/{t['id']}/act", json={"action": "APPROVE"}, headers=h)
            assert r.status_code == 200, r.text


_WORLD: dict[str, Any] = {}


@pytest.fixture
def world(client: TestClient, tenant: TenantDescriptor) -> dict[str, Any]:
    if not _WORLD:
        _WORLD.update(_build(client, tenant))
    return _WORLD


def _build(client: TestClient, tenant: TenantDescriptor) -> dict[str, Any]:
    joseph, mary = (
        make_org_unit(tenant, "ANBIYAM", "St. Joseph Anbiyam"),
        make_org_unit(tenant, "ANBIYAM", "St. Mary Anbiyam"),
    )
    youth = make_org_unit(tenant, "SOCIETY", "Youth Society")
    users = {
        "priest": make_user(tenant, "PARISH_PRIEST"),
        "secretary": make_user(tenant, "PARISH_SECRETARY"),
        "treasurer": make_user(tenant, "PARISH_TREASURER"),
        "leader": make_user(tenant, "ANBIYAM_LEADER", unit=joseph),
        "member": make_user(tenant, "GENERAL_MEMBER"),
    }
    h = login(client, users["secretary"])
    fam = register(
        client, h, "Arokiasamy", pid(tenant, joseph), [("John", "M", "HEAD", 45), ("Rita", "F", "SPOUSE", 40),
                                                        ("Ann", "F", "DAUGHTER", 10)]
    )  # fmt: skip
    register(client, h, "Fernando", pid(tenant, mary), [("Peter", "M", "HEAD", 70)])
    register(client, h, "Dias", None, [("Lucy", "F", "HEAD", 25)])
    with tenant_session_scope(tenant) as s:
        john = s.scalar(select(Member).where(Member.first_name == "John"))
        assert john
        s.get(User, users["member"].id).member_id = john.id  # type: ignore[union-attr]
        donation = s.scalar(select(FinCategory).where(FinCategory.code == "DONATION")).public_id  # type: ignore[union-attr]
        charity = s.scalar(select(FinCategory).where(FinCategory.code == "CHARITY")).public_id  # type: ignore[union-attr]
    ht = login(client, users["treasurer"])
    acc = client.post(
        "/api/v1/finance/accounts",
        json={"code": "CASHD", "name": "Cash", "kind": "CASH", "opening_balance": "0",
              "opening_date": str(TODAY.replace(day=1) - timedelta(days=40))},
        headers=ht,
    ).json()["id"]  # fmt: skip
    for cat, kind, amt, extra in (
        (donation, "INCOME", "5000", {"family_id": fam["id"]}),
        (charity, "EXPENSE", "1200", {}),
    ):
        r = client.post(
            "/api/v1/finance/transactions",
            json={"txn_date": str(TODAY), "kind": kind, "category_id": cat, "account_id": acc, "amount": amt,
                  "description": "Dashboard entry", **extra},
            headers=ht,
        )  # fmt: skip
        assert r.status_code == 201, r.text
        client.post(f"/api/v1/finance/transactions/{r.json()['id']}/submit", json={}, headers=ht)
    approve_all(client, users["treasurer"], users["priest"])
    # One more entry left pending with the Parish Priest.
    r = client.post(
        "/api/v1/finance/transactions",
        json={"txn_date": str(TODAY), "kind": "EXPENSE", "category_id": charity, "account_id": acc,
              "amount": "300", "description": "Pending entry"},
        headers=ht,
    )  # fmt: skip
    client.post(f"/api/v1/finance/transactions/{r.json()['id']}/submit", json={}, headers=ht)
    approve_all(client, users["treasurer"])
    return {"users": users, "youth": youth, "family": fam}


def test_priest_sees_everything(client: TestClient, world: dict) -> None:
    d = client.get("/api/v1/dashboard", headers=login(client, world["users"]["priest"])).json()
    assert d["people"]["families"] == 3 and d["people"]["members"] == 5
    assert d["people"]["pending_anbiyam"] == 1 and d["people"]["new_families_month"] == 3
    assert {a["name"]: a["members"] for a in d["people"]["by_anbiyam"]} == {
        "St. Joseph Anbiyam": 3,
        "St. Mary Anbiyam": 1,
    }
    bands = {b["label"]: b["value"] for b in d["people"]["age_bands"]}
    assert bands["0–12"] == 1 and bands["60+"] == 1 and sum(bands.values()) == 5
    orgs = {o["code"]: o for o in d["organisations"]}
    assert orgs["ANBIYAM"]["units"] == 2 and orgs["ANBIYAM"]["members"] == 2  # families linked to an Anbiyam
    f = d["finance"]
    assert len(f["months"]) == 12 and f["months"][-1]["income"] == "5000.00"
    assert f["months"][-1]["expense"] == "1200.00" and f["donations_fy"] == "5000.00"
    assert f["expense_by_category"][0]["name"] == "Charity" and f["pending_entries"] == 1
    assert len(f["periods"]) == 6
    a = d["approvals"]
    assert a["pending"] == 1 and a["finance"] == 1 and a["items"][0]["entity_type"] == "FIN_TRANSACTION"
    assert d["activities"] is not None and d["meetings"] is not None and d["me"] is None


def test_scoped_and_member_dashboards(client: TestClient, world: dict) -> None:
    lead = client.get("/api/v1/dashboard", headers=login(client, world["users"]["leader"])).json()
    assert lead["people"]["families"] == 1 and lead["people"]["members"] == 3  # own Anbiyam only
    assert lead["finance"] is None
    tr = client.get("/api/v1/dashboard", headers=login(client, world["users"]["treasurer"])).json()
    assert tr["finance"]["income_by_category"][0]["amount"] == "5000.00"
    me = client.get("/api/v1/dashboard", headers=login(client, world["users"]["member"])).json()
    assert me["people"] is None and me["finance"] is None and me["activities"] is None
    assert me["approvals"]["pending"] == 0
    m = me["me"]
    assert m["name"] == "John" and m["anbiyam"] == "St. Joseph Anbiyam"
    assert [x["relationship"] for x in m["household"]] == ["HEAD", "SPOUSE", "DAUGHTER"]
    assert m["donations_fy"] == "5000.00" and m["donations"][0]["category"] == "Donations"

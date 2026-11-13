"""Global search, reports and audit viewer (T15)."""

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
from app.modules.reports.base import REPORTS
from tests.conftest import auth, make_org_unit

HOST = {"Host": "rpt.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
TODAY = date.today()
_n = count(1)
_phone = count(9841000001)
_WORLD: dict[str, Any] = {}


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="RPT", name="St. Sebastian's Church"))
        s.commit()
    return provision_parish("RPT")


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    counter().reset()
    yield


def make_user(tenant: TenantDescriptor, *roles: str, unit: int | None = None) -> User:
    username = f"r{next(_n)}"
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


def register(client: TestClient, h: dict[str, str], name: str, anbiyam: str | None, people: list) -> dict:
    body = {
        "family_name": name,
        "phone": f"+91 {next(_phone)}",
        "address_line1": "5 Church Road",
        "city": "Chennai",
        "anbiyam_id": anbiyam,
        "members": [
            {"first_name": f, "gender": g, "relationship_to_head": rel,
             "date_of_birth": str(TODAY.replace(year=TODAY.year - a) - timedelta(days=5))}
            for f, g, rel, a in people
        ],
    }  # fmt: skip
    r = client.post("/api/v1/families", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def approve_all(client: TestClient, *users: User) -> None:
    for u in users:
        h = login(client, u)
        for t in client.get("/api/v1/workflow/tasks?size=100", headers=h).json()["items"]:
            assert (
                client.post(
                    f"/api/v1/workflow/tasks/{t['id']}/act", json={"action": "APPROVE"}, headers=h
                ).status_code
                == 200
            )


@pytest.fixture
def world(client: TestClient, tenant: TenantDescriptor) -> dict[str, Any]:
    if _WORLD:
        return _WORLD
    joseph = make_org_unit(tenant, "ANBIYAM", "St. Joseph Anbiyam")
    mary = make_org_unit(tenant, "ANBIYAM", "St. Mary Anbiyam")
    u = {
        "priest": make_user(tenant, "PARISH_PRIEST"),
        "secretary": make_user(tenant, "PARISH_SECRETARY"),
        "treasurer": make_user(tenant, "PARISH_TREASURER"),
        "leader": make_user(tenant, "ANBIYAM_LEADER", unit=joseph),
        "member": make_user(tenant, "GENERAL_MEMBER"),
    }
    h = login(client, u["secretary"])
    a = register(
        client, h, "Arokiasamy", pid(tenant, joseph), [("John", "M", "HEAD", 45), ("Rita", "F", "SPOUSE", 41)]
    )
    register(client, h, "Arokiaraj", pid(tenant, mary), [("Peter", "M", "HEAD", 60)])
    with tenant_session_scope(tenant) as s:
        john = s.scalar(select(Member).where(Member.first_name == "John"))
        assert john
        john.baptism_date, john.baptism_place = TODAY - timedelta(days=40), "St. Sebastian's"
        john.marriage_date, john.marriage_place = TODAY - timedelta(days=20), "St. Sebastian's"
        donation = s.scalar(select(FinCategory).where(FinCategory.code == "DONATION")).public_id  # type: ignore[union-attr]
        charity = s.scalar(select(FinCategory).where(FinCategory.code == "CHARITY")).public_id  # type: ignore[union-attr]
    ht = login(client, u["treasurer"])
    acc = client.post(
        "/api/v1/finance/accounts",
        json={"code": "CASHR", "name": "Cash", "kind": "CASH", "opening_balance": "0",
              "opening_date": str(TODAY.replace(day=1) - timedelta(days=40))},
        headers=ht,
    ).json()["id"]  # fmt: skip
    codes = []
    for cat, kind, amt, extra in (
        (donation, "INCOME", "5000", {"family_id": a["id"], "description": "Feast donation"}),
        (charity, "EXPENSE", "1200", {"description": "Flood relief"}),
    ):
        r = client.post(
            "/api/v1/finance/transactions",
            json={
                "txn_date": str(TODAY),
                "kind": kind,
                "category_id": cat,
                "account_id": acc,
                "amount": amt,
                **extra,
            },
            headers=ht,
        )
        assert r.status_code == 201, r.text
        codes.append(r.json()["code"])
        client.post(f"/api/v1/finance/transactions/{r.json()['id']}/submit", json={}, headers=ht)
    approve_all(client, u["treasurer"], u["priest"])
    _WORLD.update(users=u, family=a, codes=codes)
    return _WORLD


def test_search_is_scoped(client: TestClient, world: dict) -> None:
    u = world["users"]
    r = client.get("/api/v1/search?q=arok", headers=login(client, u["priest"])).json()
    groups = {g["key"]: g for g in r["groups"]}
    assert groups["families"]["total"] == 2
    r = client.get("/api/v1/search?q=john", headers=login(client, u["priest"])).json()
    groups = {g["key"]: g for g in r["groups"]}
    assert groups["members"]["hits"][0]["link"].startswith(f"/families/{world['family']['id']}?member=")
    lead = client.get("/api/v1/search?q=arok", headers=login(client, u["leader"])).json()
    fam = next(g for g in lead["groups"] if g["key"] == "families")
    assert [x["title"] for x in fam["hits"]] == ["Arokiasamy"]  # own Anbiyam only
    assert client.get("/api/v1/search?q=arok", headers=login(client, u["member"])).json()["groups"] == []
    code = world["codes"][1]
    fin = client.get(f"/api/v1/search?q={code}", headers=login(client, u["treasurer"])).json()["groups"]
    assert [g["key"] for g in fin] == ["finance"] or fin[0]["hits"][0]["code"] == code
    assert next(g for g in fin if g["key"] == "finance")["hits"][0]["code"] == code
    assert client.get("/api/v1/search?q=a", headers=login(client, u["priest"])).status_code == 422
    one = client.get(
        "/api/v1/search?q=arok&group=families&limit=1", headers=login(client, u["priest"])
    ).json()
    assert [g["key"] for g in one["groups"]] == ["families"] and len(one["groups"][0]["hits"]) == 1


def test_report_catalog_follows_permissions(client: TestClient, world: dict) -> None:
    u = world["users"]

    def codes(user: User) -> set[str]:
        return {r["code"] for r in client.get("/api/v1/reports", headers=login(client, user)).json()}

    assert codes(u["priest"]) == set(REPORTS)
    tr = codes(u["treasurer"])
    assert "donation_report" in tr and "sacrament_register" not in tr and "user_activity" not in tr
    assert codes(u["member"]) == set()
    h = login(client, u["member"])
    assert client.get("/api/v1/reports/family_register", headers=h).status_code == 404


def test_every_report_runs(client: TestClient, world: dict) -> None:
    h = login(client, world["users"]["priest"])
    for code in REPORTS:
        r = client.get(f"/api/v1/reports/{code}", headers=h)
        assert r.status_code == 200, (code, r.text)
        body = r.json()
        assert body["columns"] and isinstance(body["rows"], list)
    fam = client.get("/api/v1/reports/family_register", headers=h).json()
    assert fam["total_rows"] == 2 and fam["rows"][0]["members"] in (1, 2)
    don = client.get("/api/v1/reports/donation_report", headers=h).json()
    assert don["rows"][0]["donor"] == "Arokiasamy" and don["totals"]["amount"] == "5000.00"
    ie = client.get(f"/api/v1/reports/income_expenditure?month={TODAY:%Y-%m}", headers=h).json()
    assert ie["totals"] == {"category": "Surplus", "amount": "3800.00"}
    bap = client.get("/api/v1/reports/sacrament_register?sacrament=BAPTISM", headers=h).json()
    assert [x["name"] for x in bap["rows"]] == ["John"]
    assert client.get("/api/v1/reports/marriage_register", headers=h).json()["total_rows"] == 1
    lead = client.get(
        "/api/v1/reports/family_register", headers=login(client, world["users"]["leader"])
    ).json()
    assert [x["family"] for x in lead["rows"]] == ["Arokiasamy"]
    bad = client.get("/api/v1/reports/income_expenditure?date_from=2026-12-01&date_to=2026-11-01", headers=h)
    assert bad.status_code == 200  # monthly report ignores the range
    assert (
        client.get(
            "/api/v1/reports/donation_report?date_from=2026-12-01&date_to=2026-11-01", headers=h
        ).status_code
        == 422
    )


def test_exports_and_audit(client: TestClient, world: dict) -> None:
    h = login(client, world["users"]["priest"])
    for fmt, magic in (("csv", b"\xef\xbb\xbf"), ("xlsx", b"PK"), ("pdf", b"%PDF")):
        r = client.get(f"/api/v1/reports/donation_report/export?format={fmt}", headers=h)
        assert r.status_code == 200 and r.content.startswith(magic), (fmt, r.text[:200])
    csv = client.get("/api/v1/reports/family_register/export?format=csv", headers=h).content.decode(
        "utf-8-sig"
    )
    assert csv.splitlines()[0].startswith("Code,Family,Head") and "Arokiasamy" in csv
    facets = client.get("/api/v1/audit-logs/facets", headers=h).json()
    assert "REPORT_EXPORTED" in facets["actions"] and "reports" in facets["modules"]
    logs = client.get("/api/v1/audit-logs?action=REPORT_EXPORTED", headers=h).json()
    assert logs["total"] >= 4 and logs["items"][0]["entity_id"] in ("family_register", "donation_report")
    # Organisation leaders get reports for their own unit only.
    hs = login(client, world["users"]["leader"])
    assert client.get("/api/v1/reports/family_register", headers=hs).status_code == 200
    ex = client.get("/api/v1/reports/family_register/export?format=csv", headers=hs)
    assert ex.status_code == 200 and "St. Mary" not in ex.content.decode("utf-8-sig")

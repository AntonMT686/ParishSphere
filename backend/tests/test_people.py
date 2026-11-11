"""Families & members (T8): registration, duplicates, scoping, sensitive data, life events, memberships."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.common.ratelimit import counter
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.people.service import normalize_name, phone_digits
from app.modules.rbac.service import assign_role, role_by_code
from tests.conftest import auth

HOST = {"Host": "ppl.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)
_phone = count(9840000001)
TODAY = date.today()


def yrs(n: int) -> str:
    return str(TODAY.replace(year=TODAY.year - n) - timedelta(days=10))


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="PPL", name="People Parish"))
        s.commit()
    return provision_parish("PPL")


@pytest.fixture(autouse=True)
def _rl() -> Iterator[None]:
    counter().reset()
    yield


def make_user(tenant: TenantDescriptor, *roles: str) -> User:
    username = f"p{next(_n)}"
    with tenant_session_scope(tenant) as s:
        u = create_user(
            s, username=username, full_name=f"Person {username}", password=PW, must_change_password=False
        )
        for code in roles:
            r = role_by_code(s, code)
            assert r
            assign_role(s, u, r)
        s.flush()
        s.expunge(u)
    return u


def login(client: TestClient, user: User) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": user.username, "password": PW}, headers=HOST)
    assert r.status_code == 200, r.text
    return {**HOST, **auth(r.json()["access_token"])}


@pytest.fixture(scope="module")
def admin(client_module: TestClient, tenant: TenantDescriptor) -> dict[str, str]:
    return login(client_module, make_user(tenant, "PARISH_ADMIN"))


@pytest.fixture(scope="module")
def sec(client_module: TestClient, tenant: TenantDescriptor) -> dict[str, str]:
    return login(client_module, make_user(tenant, "PARISH_SECRETARY"))


@pytest.fixture(scope="module")
def client_module(app) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(app)


@pytest.fixture(scope="module")
def anbiyams(client_module: TestClient, admin: dict[str, str]) -> dict[str, str]:
    out = {}
    for name in ("St. Joseph Anbiyam", "St. Anne Anbiyam"):
        r = client_module.post(
            "/api/v1/org-units", json={"type_code": "ANBIYAM", "name": name}, headers=admin
        )
        assert r.status_code == 201, r.text
        out[name.split()[1]] = r.json()["id"]
    return out


def member(
    first: str, rel: str = "OTHER", gender: str = "M", age: int | None = 30, **kw: Any
) -> dict[str, Any]:
    return {
        "first_name": first,
        "last_name": kw.pop("last", None),
        "gender": gender,
        "relationship_to_head": rel,
        "date_of_birth": yrs(age) if age is not None else None,
        **kw,
    }


def register(
    client: TestClient,
    h: dict[str, str],
    name: str,
    anbiyam: str | None,
    members: list[dict[str, Any]],
    **kw: Any,
) -> dict[str, Any]:
    body = {
        "family_name": name,
        "phone": f"+91 {next(_phone)}",
        "address_line1": "12 Church Street",
        "city": "Chennai",
        "anbiyam_id": anbiyam,
        "members": members,
        **kw,
    }
    r = client.post("/api/v1/families", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ----------------------------------------------------------------------------- helpers
def test_normalisation() -> None:
    assert normalize_name("  Arokia-Samy ", "D'Souza") == "arokia samy d souza"
    assert normalize_name("ஆரோக்கியசாமி") == "ஆரோக்கியசாமி"
    assert phone_digits("+91 98400-12345") == "9840012345" and phone_digits("123") is None


# ----------------------------------------------------------------------------- registration
def test_register_family(client_module: TestClient, sec: dict[str, str], anbiyams: dict[str, str]) -> None:
    f = register(
        client_module,
        sec,
        "Arokiasamy",
        anbiyams["Joseph"],
        [
            member("John", "HEAD", last="Arokiasamy", age=52, phone="98400 11111", baptism_date=yrs(52)),
            member("Mary", "SPOUSE", "F", 48),
            member("Peter", "SON", age=20),
        ],
    )
    assert f["code"].startswith("FAM") and f["status"] == "ACTIVE" and f["member_count"] == 3
    assert f["anbiyam"]["name"] == "St. Joseph Anbiyam" and f["head_name"] == "John Arokiasamy"
    head = next(m for m in f["members"] if m["is_head"])
    assert head["code"].startswith("MEM") and head["phone"] == "98400 11111" and head["baptism_date"]
    assert head["sensitive_visible"] and head["sacraments_visible"]

    pending = register(client_module, sec, "New Arrivals", None, [member("Raj", "HEAD")])
    assert pending["status"] == "PENDING_ANBIYAM" and pending["anbiyam"] is None


@pytest.mark.parametrize("rels", [["SON"], ["HEAD", "HEAD"]])
def test_exactly_one_head(client_module: TestClient, sec: dict[str, str], rels: list[str]) -> None:
    r = client_module.post(
        "/api/v1/families",
        headers=sec,
        json={"family_name": "Headless", "members": [member(f"M{i}", rel) for i, rel in enumerate(rels)]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "FAMILY_HEAD_REQUIRED"


def test_duplicate_detection(
    client_module: TestClient, sec: dict[str, str], anbiyams: dict[str, str]
) -> None:
    f = register(
        client_module,
        sec,
        "Fernando",
        anbiyams["Joseph"],
        [member("Antony", "HEAD", age=40, last="Fernando")],
    )
    body = {
        "family_name": "Fernando",
        "phone": "000",
        "members": [member("Antony", "HEAD", age=40, last="Fernando")],
    }
    r = client_module.post("/api/v1/families", json=body, headers=sec)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_SUSPECTED"
    assert f["code"] in r.json()["error"]["details"][0]["message"]
    check = client_module.post(
        "/api/v1/families/check-duplicates",
        headers=sec,
        json={"family_name": "Someone Else", "members": [member("ANTONY", "HEAD", age=40, last="fernando")]},
    ).json()
    assert check[0]["family_code"] == f["code"] and "same name and date of birth" in check[0]["reasons"][0]
    same_phone = client_module.post(
        "/api/v1/families/check-duplicates", headers=sec, json={"phone": f["phone"], "members": []}
    ).json()
    assert same_phone[0]["reasons"][0].startswith("Same family phone")
    ok = client_module.post("/api/v1/families", json={**body, "confirm_not_duplicate": True}, headers=sec)
    assert ok.status_code == 201


def test_search_and_filters(client_module: TestClient, sec: dict[str, str], anbiyams: dict[str, str]) -> None:
    f = register(
        client_module,
        sec,
        "Xavier",
        anbiyams["Anne"],
        [member("Sebastian", "HEAD"), member("Lourdu", "SON")],
        family_name_local="சேவியர்",
    )
    for q in ("lourdu", f["code"], f["phone"], "சேவியர்"):
        items = client_module.get("/api/v1/families", params={"q": q}, headers=sec).json()["items"]
        assert [x["id"] for x in items] == [f["id"]], q
    items = client_module.get("/api/v1/families", params={"anbiyam": anbiyams["Anne"]}, headers=sec).json()[
        "items"
    ]
    assert f["id"] in {x["id"] for x in items}
    none = client_module.get("/api/v1/families", params={"anbiyam": "none"}, headers=sec).json()["items"]
    assert all(x["anbiyam"] is None for x in none)
    adults = client_module.get(
        "/api/v1/members", params={"q": "sebastian", "age_min": 18}, headers=sec
    ).json()
    assert adults["total"] == 1


# ----------------------------------------------------------------------------- scope & sensitive data
def test_anbiyam_leader_scope_and_field_gating(
    client_module: TestClient,
    tenant: TenantDescriptor,
    admin: dict[str, str],
    sec: dict[str, str],
    anbiyams: dict[str, str],
) -> None:
    mine = register(
        client_module, sec, "Leader Own", anbiyams["Joseph"], [member("Own", "HEAD", phone="1111111111")]
    )
    other = register(client_module, sec, "Leader Other", anbiyams["Anne"], [member("Other", "HEAD")])
    leader = make_user(tenant)
    r = client_module.post(
        f"/api/v1/org-units/{anbiyams['Joseph']}/office-bearers",
        headers=admin,
        json={"position_code": "PRESIDENT", "user_id": leader.public_id},
    )
    assert r.status_code == 201 and r.json()["grants_role"] == "Anbiyam Leader"
    lh = login(client_module, leader)

    ids = {x["id"] for x in client_module.get("/api/v1/families?size=100", headers=lh).json()["items"]}
    assert mine["id"] in ids and other["id"] not in ids
    assert client_module.get(f"/api/v1/families/{other['id']}", headers=lh).status_code == 404
    fam = client_module.get(f"/api/v1/families/{mine['id']}", headers=lh).json()
    head = fam["members"][0]
    assert head["age"] == 30 and head["date_of_birth"] is None and head["phone"] is None
    assert head["sensitive_visible"] is False and head["sacraments_visible"] is False

    # Leaders may add members (incl. date of birth at registration) to their own Anbiyam's families…
    r = client_module.post(
        f"/api/v1/families/{mine['id']}/members", headers=lh, json=member("Child", "SON", age=5)
    )
    assert r.status_code == 201 and r.json()["age"] == 5 and r.json()["date_of_birth"] is None
    child = r.json()["id"]
    # …but not record sacraments, change personal details later, or touch other Anbiyams.
    r = client_module.post(
        f"/api/v1/families/{mine['id']}/members",
        headers=lh,
        json=member("Baby", "DAUGHTER", "F", 1, baptism_date=str(TODAY)),
    )
    assert r.status_code == 403
    assert (
        client_module.patch(f"/api/v1/members/{child}", headers=lh, json={"phone": "99"}).status_code == 403
    )
    assert (
        client_module.patch(f"/api/v1/members/{child}", headers=lh, json={"name_local": "குழந்தை"}).status_code
        == 200
    )
    r = client_module.post(f"/api/v1/families/{other['id']}/members", headers=lh, json=member("X", "SON"))
    assert r.status_code == 404
    # Leaders cannot register families (no family.create) and do not see the audit-sensitive exports.
    assert (
        client_module.post(
            "/api/v1/families", headers=lh, json={"family_name": "X", "members": [member("A", "HEAD")]}
        ).status_code
        == 403
    )


def test_general_member_has_no_access(client_module: TestClient, tenant: TenantDescriptor) -> None:
    h = login(client_module, make_user(tenant, "GENERAL_MEMBER"))
    assert client_module.get("/api/v1/families", headers=h).status_code == 403
    assert client_module.get("/api/v1/members", headers=h).status_code == 403


# ----------------------------------------------------------------------------- life events
def test_change_anbiyam_and_history(
    client_module: TestClient, sec: dict[str, str], anbiyams: dict[str, str]
) -> None:
    f = register(client_module, sec, "Mover", None, [member("Mo", "HEAD")])
    r = client_module.post(
        f"/api/v1/families/{f['id']}/anbiyam", headers=sec, json={"anbiyam_id": anbiyams["Joseph"]}
    )
    assert r.json()["status"] == "ACTIVE"
    r = client_module.post(
        f"/api/v1/families/{f['id']}/anbiyam",
        headers=sec,
        json={"anbiyam_id": anbiyams["Anne"], "reason": "Moved house"},
    )
    assert r.json()["anbiyam"]["name"] == "St. Anne Anbiyam"
    same = client_module.post(
        f"/api/v1/families/{f['id']}/anbiyam", headers=sec, json={"anbiyam_id": anbiyams["Anne"]}
    )
    assert same.status_code == 422
    h = client_module.get(f"/api/v1/families/{f['id']}/history", headers=sec).json()
    assert [x["anbiyam"]["name"] for x in h["anbiyam_history"]] == ["St. Anne Anbiyam", "St. Joseph Anbiyam"]
    assert h["anbiyam_history"][1]["valid_to"] is not None
    assert [e["event_type"] for e in h["events"]][:3] == ["ANBIYAM_CHANGED", "ANBIYAM_CHANGED", "REGISTERED"]


def test_head_deceased_and_new_head(
    client_module: TestClient, sec: dict[str, str], admin: dict[str, str], anbiyams: dict[str, str]
) -> None:
    f = register(
        client_module,
        sec,
        "Sorrow",
        anbiyams["Joseph"],
        [member("Father", "HEAD", age=80), member("Mother", "SPOUSE", "F", 75)],
    )
    head = next(m for m in f["members"] if m["is_head"])
    wife = next(m for m in f["members"] if not m["is_head"])
    soc = client_module.post(
        "/api/v1/org-units", json={"type_code": "SOCIETY", "name": "Senior Fellowship"}, headers=admin
    ).json()
    assert (
        client_module.post(
            f"/api/v1/org-units/{soc['id']}/memberships", headers=admin, json={"member_id": head["id"]}
        ).status_code
        == 201
    )
    r = client_module.post(
        f"/api/v1/members/{head['id']}/deceased",
        headers=sec,
        json={"date_of_death": str(TODAY), "remarks": "RIP"},
    )
    assert r.json()["status"] == "DECEASED"
    fam = client_module.get(f"/api/v1/families/{f['id']}", headers=sec).json()
    assert fam["head_member_id"] is None and fam["member_count"] == 1
    assert client_module.get(f"/api/v1/org-units/{soc['id']}/memberships", headers=admin).json()["total"] == 0
    again = client_module.post(
        f"/api/v1/members/{head['id']}/deceased", headers=sec, json={"date_of_death": str(TODAY)}
    )
    assert again.status_code == 409
    r = client_module.post(f"/api/v1/families/{f['id']}/head", headers=sec, json={"member_id": wife["id"]})
    assert r.json()["head_name"] == "Mother"
    # The deceased former head no longer counts as HEAD: exactly one HEAD remains.
    rels = {m["first_name"]: m["relationship_to_head"] for m in r.json()["members"]}
    assert rels == {"Father": "OTHER", "Mother": "HEAD"}
    dead = client_module.post(f"/api/v1/families/{f['id']}/head", headers=sec, json={"member_id": head["id"]})
    assert dead.status_code == 422


def test_move_member_requires_new_head(
    client_module: TestClient, sec: dict[str, str], tenant: TenantDescriptor, anbiyams: dict[str, str]
) -> None:
    a = register(
        client_module,
        sec,
        "Origin",
        anbiyams["Joseph"],
        [member("Boss", "HEAD"), member("Kid", "SON", age=25)],
    )
    b = register(client_module, sec, "Target", anbiyams["Joseph"], [member("Receiver", "HEAD")])
    boss = next(m for m in a["members"] if m["is_head"])
    kid = next(m for m in a["members"] if not m["is_head"])
    xfer = login(client_module, make_user(tenant, "PARISH_SECRETARY"))
    r = client_module.post(
        f"/api/v1/members/{boss['id']}/move",
        headers=xfer,
        json={"family_id": b["id"], "relationship_to_head": "BROTHER"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "FAMILY_HEAD_REQUIRED"
    r = client_module.post(
        f"/api/v1/members/{boss['id']}/move",
        headers=xfer,
        json={"family_id": b["id"], "relationship_to_head": "BROTHER", "new_head_member_id": kid["id"]},
    )
    assert r.status_code == 200 and r.json()["family"]["id"] == b["id"]
    assert client_module.get(f"/api/v1/families/{a['id']}", headers=sec).json()["head_name"] == "Kid"
    assert client_module.get(f"/api/v1/families/{b['id']}", headers=sec).json()["member_count"] == 2


def test_merge_and_split(client_module: TestClient, sec: dict[str, str], anbiyams: dict[str, str]) -> None:
    dup = register(client_module, sec, "Dup Copy", anbiyams["Anne"], [member("Dupe", "HEAD")])
    main = register(client_module, sec, "Main Record", anbiyams["Anne"], [member("Main", "HEAD")])
    r = client_module.post(
        f"/api/v1/families/{dup['id']}/merge",
        headers=sec,
        json={"into_family_id": main["id"], "reason": "Registered twice"},
    )
    assert r.status_code == 200 and r.json()["member_count"] == 2
    merged = client_module.get(f"/api/v1/families/{dup['id']}", headers=sec).json()
    assert (
        merged["status"] == "MERGED"
        and merged["merged_into"]["id"] == main["id"]
        and merged["member_count"] == 0
    )
    assert (
        client_module.post(
            f"/api/v1/families/{dup['id']}/members", headers=sec, json=member("Late", "SON")
        ).status_code
        == 409
    )
    assert (
        client_module.post(
            f"/api/v1/families/{main['id']}/merge", headers=sec, json={"into_family_id": main["id"]}
        ).status_code
        == 422
    )

    big = register(
        client_module,
        sec,
        "Big House",
        anbiyams["Joseph"],
        [
            member("Grandpa", "HEAD", age=70),
            member("Son", "SON", age=35),
            member("Daughter-in-law", "DAUGHTER_IN_LAW", "F", 32),
            member("Grandkid", "GRANDSON", age=6),
        ],
    )
    ids = {m["first_name"]: m["id"] for m in big["members"]}
    r = client_module.post(
        f"/api/v1/families/{big['id']}/split",
        headers=sec,
        json={
            "member_ids": [ids["Son"], ids["Daughter-in-law"], ids["Grandkid"]],
            "head_member_id": ids["Son"],
            "new_family": {"family_name": "Son's House", "address_line1": "4 New Street"},
            "reason": "Marriage",
        },
    )
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["family_name"] == "Son's House" and new["member_count"] == 3 and new["head_name"] == "Son"
    assert new["anbiyam"]["id"] == anbiyams["Joseph"] and new["city"] == "Chennai"  # inherited
    assert client_module.get(f"/api/v1/families/{big['id']}", headers=sec).json()["member_count"] == 1
    # Moving the head out requires a head for those who remain.
    fam = register(client_module, sec, "Two", None, [member("H", "HEAD"), member("S", "SON")])
    ids = {m["first_name"]: m["id"] for m in fam["members"]}
    r = client_module.post(
        f"/api/v1/families/{fam['id']}/split",
        headers=sec,
        json={"member_ids": [ids["H"]], "head_member_id": ids["H"]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "FAMILY_HEAD_REQUIRED"


def test_transfer_out(client_module: TestClient, sec: dict[str, str], anbiyams: dict[str, str]) -> None:
    f = register(
        client_module, sec, "Leaving", anbiyams["Anne"], [member("Goer", "HEAD"), member("Kid", "SON")]
    )
    r = client_module.post(
        f"/api/v1/families/{f['id']}/transfer-out",
        headers=sec,
        json={"to_parish": "St. Thomas, Mylapore", "reason": "Relocated"},
    )
    out = r.json()
    assert out["status"] == "TRANSFERRED_OUT" and all(
        m["status"] == "TRANSFERRED_OUT" for m in out["members"]
    )
    assert (
        client_module.post(
            f"/api/v1/families/{f['id']}/transfer-out", headers=sec, json={"to_parish": "Again"}
        ).status_code
        == 409
    )


# ----------------------------------------------------------------------------- memberships
def test_membership_rules(
    client_module: TestClient, admin: dict[str, str], sec: dict[str, str], anbiyams: dict[str, str]
) -> None:
    types = client_module.get("/api/v1/org-unit-types", headers=admin).json()
    soc_type = next(t for t in types if t["code"] == "SOCIETY")
    client_module.patch(
        f"/api/v1/org-unit-types/{soc_type['id']}",
        headers=admin,
        json={"membership_rules": {"min_age": 15, "max_age": 35, "max_units_per_member": 2}},
    )
    youth = client_module.post(
        "/api/v1/org-units", json={"type_code": "SOCIETY", "name": "Youth"}, headers=admin
    ).json()
    f = register(
        client_module,
        sec,
        "Young Ones",
        anbiyams["Joseph"],
        [
            member("Dad", "HEAD", age=50),
            member("Teen", "SON", age=18),
            member("Tiny", "DAUGHTER", "F", 8),
            member("Nodob", "SON", age=None),
        ],
    )
    ids = {m["first_name"]: m["id"] for m in f["members"]}
    url = f"/api/v1/org-units/{youth['id']}/memberships"
    r = client_module.post(url, headers=admin, json={"member_id": ids["Tiny"]})
    assert (
        r.status_code == 422
        and r.json()["error"]["code"] == "MEMBERSHIP_RULES"
        and "Minimum age is 15" in r.text
    )
    assert "Maximum age is 35" in client_module.post(url, headers=admin, json={"member_id": ids["Dad"]}).text
    assert (
        "Date of birth is required"
        in client_module.post(url, headers=admin, json={"member_id": ids["Nodob"]}).text
    )
    ok = client_module.post(url, headers=admin, json={"member_id": ids["Teen"]})
    assert ok.status_code == 201 and ok.json()["age"] == 18
    assert (
        client_module.post(url, headers=admin, json={"member_id": ids["Teen"]}).json()["error"]["code"]
        == "ALREADY_MEMBER"
    )
    assert client_module.post(url, headers=admin, json={"family_id": f["id"]}).status_code == 422
    for name in ("Choir", "Altar"):
        unit = client_module.post(
            "/api/v1/org-units", json={"type_code": "SOCIETY", "name": name}, headers=admin
        ).json()
        res = client_module.post(
            f"/api/v1/org-units/{unit['id']}/memberships", headers=admin, json={"member_id": ids["Teen"]}
        )
    assert res.status_code == 422 and "at most 2" in res.text  # Youth + Choir allowed, Altar refused

    mships = client_module.get(f"/api/v1/members/{ids['Teen']}/memberships", headers=sec).json()
    assert [x["org_unit"]["name"] for x in mships][:1] == ["St. Joseph Anbiyam"]  # Anbiyam via family
    end = client_module.post(f"{url}/{ok.json()['id']}/end", headers=admin, json={"reason": "Moved away"})
    assert end.json()["current"] is False
    hist = client_module.get(f"{url}?include_history=true", headers=admin).json()
    assert hist["items"][0]["left_on"] == str(TODAY)
    client_module.patch(
        f"/api/v1/org-unit-types/{soc_type['id']}", headers=admin, json={"membership_rules": {}}
    )

    anb = client_module.get(
        f"/api/v1/org-units/{anbiyams['Joseph']}/memberships?q=young", headers=admin
    ).json()
    assert [x["family"]["name"] for x in anb["items"]] == ["Young Ones"]
    r = client_module.post(
        f"/api/v1/org-units/{anbiyams['Joseph']}/memberships", headers=admin, json={"family_id": f["id"]}
    )
    assert r.json()["error"]["code"] == "USE_FAMILY_ANBIYAM"


def test_office_bearer_from_register(
    client_module: TestClient, admin: dict[str, str], sec: dict[str, str]
) -> None:
    f = register(client_module, sec, "Choir Family", None, [member("Singer", "HEAD", last="Raj")])
    unit = client_module.post(
        "/api/v1/org-units", json={"type_code": "COMMITTEE", "name": "Liturgy"}, headers=admin
    ).json()
    r = client_module.post(
        f"/api/v1/org-units/{unit['id']}/office-bearers",
        headers=admin,
        json={"position_code": "EXECUTIVE_MEMBER", "member_id": f["members"][0]["id"]},
    )
    assert r.status_code == 201 and r.json()["holder_name"] == "Singer Raj"


# ----------------------------------------------------------------------------- exports & admin view
def test_exports(client_module: TestClient, sec: dict[str, str], admin: dict[str, str]) -> None:
    from openpyxl import load_workbook

    r = client_module.get("/api/v1/families/export?format=xlsx", headers=sec)
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws["A1"].value == "Family ID" and ws.max_row > 5
    r = client_module.get("/api/v1/members/export?format=csv", headers=sec)
    assert "Date of birth" in r.text.splitlines()[0]
    r = client_module.get(
        "/api/v1/members/export?format=csv", headers=admin
    )  # admin: no member.view_sensitive
    assert "Date of birth" not in r.text.splitlines()[0]


def test_admin_sees_no_sensitive_fields(
    client_module: TestClient, admin: dict[str, str], sec: dict[str, str]
) -> None:
    f = register(
        client_module,
        sec,
        "Private",
        None,
        [member("Secret", "HEAD", phone="9999999999", baptism_date=yrs(30))],
    )
    m = client_module.get(f"/api/v1/members/{f['members'][0]['id']}", headers=admin).json()
    assert m["phone"] is None and m["baptism_date"] is None and m["age"] == 30


def test_delete_member_entered_by_mistake(client_module: TestClient, sec: dict[str, str]) -> None:
    f = register(client_module, sec, "Typo", None, [member("Real", "HEAD"), member("Oops", "SON")])
    oops = next(m for m in f["members"] if m["first_name"] == "Oops")
    head = next(m for m in f["members"] if m["is_head"])
    assert client_module.delete(f"/api/v1/members/{head['id']}", headers=sec).status_code == 422
    assert client_module.delete(f"/api/v1/members/{oops['id']}", headers=sec).status_code == 204
    assert client_module.get(f"/api/v1/members/{oops['id']}", headers=sec).status_code == 404

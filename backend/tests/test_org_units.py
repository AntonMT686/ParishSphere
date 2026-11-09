"""Configurable organisations (T7): types, units, tree, office bearers → roles, scoping."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.ratelimit import counter
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.org_units.models import OrgUnitPosition, OrgUnitType
from app.modules.org_units.service import DEFAULT_TYPES
from app.modules.rbac.service import assign_role, effective_permissions, role_by_code, users_with_permission
from tests.conftest import auth

HOST = {"Host": "org.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="ORG", name="Organisation Parish"))
        s.commit()
    return provision_parish("ORG")


@pytest.fixture(autouse=True)
def _rl() -> Iterator[None]:
    counter().reset()
    yield


def make_user(tenant: TenantDescriptor, *roles: str) -> User:
    username = f"o{next(_n)}"
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
def admin(tenant: TenantDescriptor) -> User:
    return make_user(tenant, "PARISH_ADMIN")


def create_unit(client: TestClient, h: dict[str, str], type_code: str, name: str, **extra: object) -> dict:  # type: ignore[type-arg]
    r = client.post("/api/v1/org-units", json={"type_code": type_code, "name": name, **extra}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def user_public_id(tenant: TenantDescriptor, user: User) -> str:
    return user.public_id


# ----------------------------------------------------------------------------- seeding
def test_default_types_and_positions_seeded(tenant: TenantDescriptor) -> None:
    with tenant_session_scope(tenant) as s:
        types = {t.code: t for t in s.scalars(select(OrgUnitType))}
        assert set(types) == {d.code for d in DEFAULT_TYPES}
        assert types["ANBIYAM"].member_kind == "FAMILY" and not types["COUNCIL"].allow_multiple_units
        pos = {
            p.code: p
            for p in s.scalars(select(OrgUnitPosition).where(OrgUnitPosition.type_id == types["SOCIETY"].id))
        }
        president_role = role_by_code(s, "SOCIETY_LEADER")
        assert president_role and pos["PRESIDENT"].role_id == president_role.id
        council_sec = s.scalars(
            select(OrgUnitPosition).where(
                OrgUnitPosition.type_id == types["COUNCIL"].id, OrgUnitPosition.code == "SECRETARY"
            )
        ).one()
        assert council_sec.role_id == role_by_code(s, "PARISH_SECRETARY").id  # type: ignore[union-attr]


def test_types_api(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    h = login(client, admin)
    types = client.get("/api/v1/org-unit-types", headers=h).json()
    assert [t["code"] for t in types][:3] == ["COUNCIL", "COMMITTEE", "ANBIYAM"]
    r = client.post(
        "/api/v1/org-unit-types",
        headers=h,
        json={
            "code": "zone",
            "name": "Zone",
            "name_plural": "Zones",
            "code_prefix": "zn",
            "membership_rules": {"min_age": 18},
            "positions": [{"code": "coordinator", "name": "Coordinator", "role_code": "COMMITTEE_PRESIDENT"}],
        },
    )
    assert r.status_code == 201, r.text
    zone = r.json()
    assert zone["code"] == "ZONE" and zone["positions"][0]["role_code"] == "COMMITTEE_PRESIDENT"
    assert zone["membership_rules"] == {"min_age": 18}
    r = client.post(
        f"/api/v1/org-unit-types/{zone['id']}/positions",
        headers=h,
        json={"code": "SECRETARY", "name": "Secretary", "role_code": "NOPE"},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/v1/org-unit-types/{zone['id']}/positions",
        headers=h,
        json={"code": "SECRETARY", "name": "Secretary", "role_code": "COMMITTEE_SECRETARY"},
    )
    assert len(r.json()["positions"]) == 2
    pid = r.json()["positions"][1]["id"]
    r = client.patch(
        f"/api/v1/org-unit-types/{zone['id']}/positions/{pid}", headers=h, json={"max_holders": 2}
    )
    assert r.json()["positions"][1]["max_holders"] == 2
    assert client.delete(f"/api/v1/org-unit-types/{zone['id']}/positions/{pid}", headers=h).status_code == 204
    council = next(t for t in types if t["code"] == "COUNCIL")
    assert (
        client.delete(f"/api/v1/org-unit-types/{council['id']}", headers=h).json()["error"]["code"]
        == "SYSTEM_TYPE"
    )
    assert client.delete(f"/api/v1/org-unit-types/{zone['id']}", headers=h).status_code == 204


# ----------------------------------------------------------------------------- units
def test_unit_lifecycle_and_tree(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    h = login(client, admin)
    council = create_unit(client, h, "COUNCIL", "Parish Pastoral Council")
    assert council["code"].startswith("PC-")
    r = client.post("/api/v1/org-units", json={"type_code": "COUNCIL", "name": "Second council"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SINGLE_UNIT_TYPE"

    zone = create_unit(
        client, h, "ANBIYAM", "St. Joseph Zone", code="anb-z1", name_local="புனித யோசேப்பு மண்டலம்"
    )
    assert zone["code"] == "ANB-Z1"
    group = create_unit(client, h, "ANBIYAM", "St. Joseph Group A", parent_id=zone["id"])
    assert group["parent"]["id"] == zone["id"]
    dup = client.post(
        "/api/v1/org-units", json={"type_code": "ANBIYAM", "name": "Duplicate", "code": "ANB-Z1"}, headers=h
    )
    assert dup.status_code == 409

    # Cycles are rejected.
    r = client.patch(f"/api/v1/org-units/{zone['id']}", json={"parent_id": group["id"]}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ORG_UNIT_CYCLE"

    r = client.get(f"/api/v1/org-units?type=anbiyam&parent={zone['id']}", headers=h).json()
    assert [u["id"] for u in r["items"]] == [group["id"]]
    assert client.get(f"/api/v1/org-units/{zone['id']}", headers=h).json()["sub_unit_count"] == 1
    r = client.get("/api/v1/org-units?q=புனித", headers=h).json()
    assert r["total"] == 1

    r = client.post(f"/api/v1/org-units/{zone['id']}/archive", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HAS_ACTIVE_SUB_UNITS"
    assert client.post(f"/api/v1/org-units/{group['id']}/archive", headers=h).json()["status"] == "INACTIVE"
    assert client.post(f"/api/v1/org-units/{zone['id']}/archive", headers=h).json()["status"] == "INACTIVE"
    r = client.post(f"/api/v1/org-units/{group['id']}/activate", headers=h)
    assert r.status_code == 409  # parent inactive
    assert client.post(f"/api/v1/org-units/{zone['id']}/activate", headers=h).json()["status"] == "ACTIVE"

    scratch = create_unit(client, h, "COMMITTEE", "Created by mistake")
    assert client.delete(f"/api/v1/org-units/{scratch['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/org-units/{scratch['id']}", headers=h).status_code == 404


# ----------------------------------------------------------------------------- office bearers & roles
def test_office_bearer_grants_scoped_role(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    h = login(client, admin)
    youth = create_unit(client, h, "SOCIETY", "Youth Society")
    women = create_unit(client, h, "SOCIETY", "Women's Society")
    secretary = make_user(tenant)

    r = client.post(
        f"/api/v1/org-units/{youth['id']}/office-bearers",
        headers=h,
        json={"position_code": "secretary", "user_id": secretary.public_id},
    )
    assert r.status_code == 201, r.text
    bearer = r.json()
    assert bearer["current"] and bearer["grants_role"] == "Committee Secretary"

    with tenant_session_scope(tenant) as s:
        user = s.get(User, secretary.id)
        assert user
        eff = effective_permissions(s, user)
        from app.modules.org_units.service import get_unit

        youth_id, women_id = get_unit(s, youth["id"]).id, get_unit(s, women["id"]).id
        assert eff.has("activity.create", youth_id) and not eff.has("activity.create", women_id)
        assert eff.role_codes == {"COMMITTEE_SECRETARY"}

    # The secretary now sees only their own society.
    sh = login(client, secretary)
    listed = client.get("/api/v1/org-units", headers=sh).json()
    assert [u["id"] for u in listed["items"]] == [youth["id"]]
    assert client.get(f"/api/v1/org-units/{women['id']}", headers=sh).status_code == 404

    # Position capacity and duplicates.
    other = make_user(tenant)
    r = client.post(
        f"/api/v1/org-units/{youth['id']}/office-bearers",
        headers=h,
        json={"position_code": "SECRETARY", "user_id": other.public_id},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "POSITION_FULL"
    r = client.post(
        f"/api/v1/org-units/{youth['id']}/office-bearers",
        headers=h,
        json={"position_code": "EXECUTIVE_MEMBER", "holder_name": "Mr. No Login"},
    )
    assert r.status_code == 201 and r.json()["grants_role"] is None

    # Ending the term ends the role (history kept).
    r = client.post(f"/api/v1/org-units/{youth['id']}/office-bearers/{bearer['id']}/end", headers=h, json={})
    assert r.status_code == 200 and r.json()["current"] is False
    assert client.get("/api/v1/org-units", headers=sh).status_code == 403
    hist = client.get(
        f"/api/v1/org-units/{youth['id']}/office-bearers?include_history=true", headers=h
    ).json()
    assert {b["holder_name"] for b in hist} >= {secretary.full_name, "Mr. No Login"}
    current = client.get(f"/api/v1/org-units/{youth['id']}", headers=h).json()["office_bearers"]
    assert [b["holder_name"] for b in current] == ["Mr. No Login"]
    # Position free again.
    r = client.post(
        f"/api/v1/org-units/{youth['id']}/office-bearers",
        headers=h,
        json={"position_code": "SECRETARY", "user_id": other.public_id},
    )
    assert r.status_code == 201


def test_council_positions_grant_parish_roles(
    client: TestClient, tenant: TenantDescriptor, admin: User
) -> None:
    h = login(client, admin)
    council = client.get("/api/v1/org-units?type=COUNCIL", headers=h).json()["items"][0]
    treasurer = make_user(tenant)
    r = client.post(
        f"/api/v1/org-units/{council['id']}/office-bearers",
        headers=h,
        json={
            "position_code": "TREASURER",
            "user_id": treasurer.public_id,
            "valid_from": str(date.today() - timedelta(days=10)),
        },
    )
    assert r.status_code == 201 and r.json()["grants_role"] == "Parish Treasurer"
    roles = client.get(f"/api/v1/users/{treasurer.public_id}/roles", headers=h).json()
    assert roles[0]["role_code"] == "PARISH_TREASURER" and roles[0]["org_unit_id"] is None
    me = client.get("/api/v1/auth/me", headers=login(client, treasurer)).json()
    assert "finance.create" in me["permissions"]


def test_scoped_manager_rules(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    h = login(client, admin)
    choir = create_unit(client, h, "SOCIETY", "Choir")
    president = make_user(tenant)
    client.post(
        f"/api/v1/org-units/{choir['id']}/office-bearers",
        headers=h,
        json={"position_code": "PRESIDENT", "user_id": president.public_id},
    )
    ph = login(client, president)
    # Society president may manage office bearers of their own society…
    secretary = make_user(tenant)
    r = client.post(
        f"/api/v1/org-units/{choir['id']}/office-bearers",
        headers=ph,
        json={"position_code": "SECRETARY", "user_id": secretary.public_id},
    )
    assert r.status_code == 201, r.text
    # …but cannot appoint themselves to a role-granting position…
    r = client.post(
        f"/api/v1/org-units/{choir['id']}/office-bearers",
        headers=ph,
        json={"position_code": "TREASURER", "user_id": president.public_id},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_MODIFICATION"
    # …nor touch another society, nor create units, nor move theirs.
    other = create_unit(client, h, "SOCIETY", "Legion of Mary")
    r = client.post(
        f"/api/v1/org-units/{other['id']}/office-bearers",
        headers=ph,
        json={"position_code": "SECRETARY", "holder_name": "X"},
    )
    assert r.status_code == 404
    assert (
        client.post(
            "/api/v1/org-units", headers=ph, json={"type_code": "SOCIETY", "name": "Mine"}
        ).status_code
        == 403
    )
    r = client.patch(f"/api/v1/org-units/{choir['id']}", headers=ph, json={"parent_id": other["id"]})
    assert r.status_code == 403
    # Society presidents do not hold org_unit.update, so they cannot edit the unit details either.
    assert (
        client.patch(
            f"/api/v1/org-units/{choir['id']}", headers=ph, json={"meeting_place": "Hall"}
        ).status_code
        == 403
    )


def test_roles_flow_to_sub_units(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    h = login(client, admin)
    zone = create_unit(client, h, "ANBIYAM", "Our Lady Zone")
    group = create_unit(client, h, "ANBIYAM", "Our Lady Group 1", parent_id=zone["id"])
    leader = make_user(tenant)
    client.post(
        f"/api/v1/org-units/{zone['id']}/office-bearers",
        headers=h,
        json={"position_code": "PRESIDENT", "user_id": leader.public_id},
    )
    lh = login(client, leader)
    ids = {u["id"] for u in client.get("/api/v1/org-units?size=100", headers=lh).json()["items"]}
    assert ids == {zone["id"], group["id"]}
    with tenant_session_scope(tenant) as s:
        from app.modules.org_units.service import get_unit

        gid = get_unit(s, group["id"]).id
        assert leader.id in {u.id for u in users_with_permission(s, "activity.review", gid)}


def test_org_scoped_role_assignment_via_users_api(
    client: TestClient, tenant: TenantDescriptor, admin: User
) -> None:
    h = login(client, admin)
    committee = create_unit(client, h, "COMMITTEE", "Festival Committee")
    u = make_user(tenant)
    r = client.post(
        f"/api/v1/users/{u.public_id}/roles",
        headers=h,
        json={"role_code": "COMMITTEE_TREASURER", "org_unit_id": committee["id"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["org_unit_id"] == committee["id"]
    r = client.post(
        f"/api/v1/users/{u.public_id}/roles",
        headers=h,
        json={"role_code": "COMMITTEE_TREASURER", "org_unit_id": "01NOTAREALUNIT0000000000000"},
    )
    assert r.status_code == 422


def test_view_permission_required(client: TestClient, tenant: TenantDescriptor) -> None:
    nobody = make_user(tenant, "GENERAL_MEMBER")
    assert client.get("/api/v1/org-units", headers=login(client, nobody)).status_code == 403
    assert client.get("/api/v1/org-unit-types", headers=login(client, nobody)).status_code == 403


def test_user_lookup_for_pickers(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    h = login(client, admin)
    unit = create_unit(client, h, "SOCIETY", "Altar Servers")
    president = make_user(tenant)
    client.post(
        f"/api/v1/org-units/{unit['id']}/office-bearers",
        headers=h,
        json={"position_code": "PRESIDENT", "user_id": president.public_id},
    )
    found = client.get(
        f"/api/v1/users/lookup?q={president.username}", headers=login(client, president)
    ).json()
    assert found == [
        {"id": president.public_id, "username": president.username, "full_name": president.full_name}
    ]
    member = make_user(tenant, "GENERAL_MEMBER")
    assert client.get("/api/v1/users/lookup?q=ab", headers=login(client, member)).status_code == 403


def test_unlimited_positions_seeded_as_unlimited(tenant: TenantDescriptor) -> None:
    with tenant_session_scope(tenant) as s:
        council = s.scalars(select(OrgUnitType).where(OrgUnitType.code == "COUNCIL")).one()
        pos = {
            p.code: p.max_holders
            for p in s.scalars(select(OrgUnitPosition).where(OrgUnitPosition.type_id == council.id))
        }
        assert pos["COUNCIL_MEMBER"] is None and pos["PRESIDENT"] == 1

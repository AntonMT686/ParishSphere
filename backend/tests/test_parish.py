"""Parish profile & priests (T9)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient

from app.common.ratelimit import counter
from app.common.storage import reset_storage
from app.core.config import get_settings
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.rbac.service import assign_role, effective_permissions, role_by_code
from tests.conftest import auth

HOST = {"Host": "par.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)
TODAY = date.today()
PNG = bytes.fromhex("89504E470D0A1A0A0000000D49484452") + b"\x00" * 64


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="PAR", name="Sacred Heart Church"))
        s.commit()
    return provision_parish("PAR")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # type: ignore[no-untyped-def]
    counter().reset()
    monkeypatch.setattr(get_settings(), "storage_local_dir", tmp_path / "files")
    reset_storage()
    yield
    reset_storage()


def make_user(tenant: TenantDescriptor, *roles: str) -> User:
    username = f"r{next(_n)}"
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


def roles_of(tenant: TenantDescriptor, user: User) -> set[str]:
    with tenant_session_scope(tenant) as s:
        u = s.get(User, user.id)
        assert u
        return effective_permissions(s, u).role_codes


# ----------------------------------------------------------------------------- profile
def test_profile_seeded_and_visible_to_everyone(client: TestClient, tenant: TenantDescriptor) -> None:
    h = login(client, make_user(tenant, "GENERAL_MEMBER"))
    p = client.get("/api/v1/parish/profile", headers=h).json()
    assert p["name"] == "Sacred Heart Church" and p["fy_start_month"] == 4 and p["currency"] == "INR"
    assert p["code"] == "PAR" and p["diocese_name"] == "Chennai Diocese" and p["parish_priest"] is None
    assert client.patch("/api/v1/parish/profile", headers=h, json={"patron_saint": "X"}).status_code == 403


def test_profile_update_syncs_branding(client: TestClient, tenant: TenantDescriptor) -> None:
    h = login(client, make_user(tenant, "PARISH_ADMIN"))
    r = client.patch(
        "/api/v1/parish/profile",
        headers=h,
        json={
            "name": "Sacred Heart Shrine",
            "name_local": "திரு இருதய ஆலயம்",
            "patron_saint": "Sacred Heart of Jesus",
            "primary_color": "#7B1E3A",
            "default_language": "ta",
            "fy_start_month": 1,
            "city": "Chennai",
            "website": "https://sacredheart.example.org",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["name_local"] == "திரு இருதய ஆலயம்" and r.json()["fy_start_month"] == 1
    b = client.get("/api/v1/tenant/branding", headers=HOST).json()
    assert b["display_name"] == "Sacred Heart Shrine" and b["primary_color"] == "#7B1E3A"
    assert b["default_language"] == "ta" and b["name"] == "Sacred Heart Shrine"
    bad = client.patch(
        "/api/v1/parish/profile", headers=h, json={"primary_color": "red", "fy_start_month": 13}
    )
    assert bad.status_code == 422
    assert client.patch("/api/v1/parish/profile", headers=h, json={"name": None}).status_code == 422
    audit = client.get("/api/v1/audit-logs?module=parish&action=UPDATE", headers=h).json()
    assert audit["total"] >= 1


def test_logo_upload_and_public_endpoint(client: TestClient, tenant: TenantDescriptor) -> None:
    h = login(client, make_user(tenant, "PARISH_ADMIN"))
    assert client.get("/api/v1/tenant/logo", headers=HOST).status_code == 404
    r = client.post("/api/v1/parish/profile/logo", headers=h, files={"file": ("logo.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["logo_url"]
    assert url.startswith("/api/v1/tenant/logo?v=")
    assert client.get("/api/v1/tenant/branding", headers=HOST).json()["logo_url"] == url
    img = client.get(url, headers=HOST)  # public: no token needed (login page)
    assert img.status_code == 200 and img.content == PNG and img.headers["content-type"] == "image/png"
    # The logo of one parish is never served on another parish's host.
    other = client.get(url, headers={"Host": "stmarys.parishsphere.test"})
    assert other.status_code in (404,) or other.content != PNG
    fake = client.post(
        "/api/v1/parish/profile/logo", headers=h, files={"file": ("logo.png", b"%PDF-1.4 x", "image/png")}
    )
    assert fake.status_code == 422 and fake.json()["error"]["code"] == "INVALID_FILE_TYPE"
    pdf = client.post(
        "/api/v1/parish/profile/logo",
        headers=h,
        files={"file": ("logo.pdf", b"%PDF-1.4 x", "application/pdf")},
    )
    assert pdf.status_code == 422
    r = client.delete("/api/v1/parish/profile/logo", headers=h)
    assert r.json()["logo_url"] is None
    assert client.get("/api/v1/tenant/logo", headers=HOST).status_code == 404


# ----------------------------------------------------------------------------- priests
def new_priest(client: TestClient, h: dict[str, str], name: str, **kw: object) -> dict:  # type: ignore[type-arg]
    r = client.post("/api/v1/priests", headers=h, json={"full_name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_priest_crud_and_permissions(client: TestClient, tenant: TenantDescriptor) -> None:
    admin = login(client, make_user(tenant, "PARISH_ADMIN"))
    p = new_priest(
        client,
        admin,
        "Antony Raj",
        ordination_date="2001-05-01",
        clergy_type="RELIGIOUS",
        congregation="Society of Jesus",
        name_local="அந்தோணி ராஜ்",
    )
    assert p["display_name"] == "Rev. Fr. Antony Raj" and p["status"] == "ACTIVE" and p["assignments"] == []
    r = client.patch(
        f"/api/v1/priests/{p['id']}", headers=admin, json={"title": "Rt. Rev. Msgr.", "phone": "98400"}
    )
    assert r.json()["display_name"] == "Rt. Rev. Msgr. Antony Raj"
    assert client.get("/api/v1/priests?q=jesus", headers=admin).json()["total"] == 1
    sec = login(client, make_user(tenant, "PARISH_SECRETARY"))
    assert client.get("/api/v1/priests", headers=sec).status_code == 200  # priest.view
    assert client.post("/api/v1/priests", headers=sec, json={"full_name": "X Y"}).status_code == 403
    member = login(client, make_user(tenant, "GENERAL_MEMBER"))
    assert client.get("/api/v1/priests", headers=member).status_code == 403


def test_single_parish_priest_and_succession(client: TestClient, tenant: TenantDescriptor) -> None:
    admin = login(client, make_user(tenant, "PARISH_ADMIN"))
    old = new_priest(client, admin, "Old Pastor")
    new = new_priest(client, admin, "New Pastor")
    start = str(TODAY - timedelta(days=400))
    r = client.post(
        f"/api/v1/priests/{old['id']}/assignments",
        headers=admin,
        json={"role": "PARISH_PRIEST", "appointed_on": start, "appointment_ref": "BP/2025/14"},
    )
    assert r.status_code == 201 and r.json()["current_roles"] == ["PARISH_PRIEST"]
    dup = client.post(
        f"/api/v1/priests/{old['id']}/assignments",
        headers=admin,
        json={"role": "PARISH_PRIEST", "appointed_on": str(TODAY)},
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "ALREADY_ASSIGNED"
    clash = client.post(
        f"/api/v1/priests/{new['id']}/assignments",
        headers=admin,
        json={"role": "PARISH_PRIEST", "appointed_on": str(TODAY)},
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "CURRENT_PARISH_PRIEST_EXISTS"
    ok = client.post(
        f"/api/v1/priests/{new['id']}/assignments",
        headers=admin,
        json={"role": "PARISH_PRIEST", "appointed_on": str(TODAY), "relieve_current": True},
    )
    assert ok.status_code == 201
    hist = client.get(f"/api/v1/priests/{old['id']}", headers=admin).json()["assignments"][0]
    assert hist["relieved_on"] == str(TODAY) and "New Pastor" in hist["relieving_reason"]  # same-day handover
    assert hist["current"] is False

    member = login(client, make_user(tenant, "GENERAL_MEMBER"))
    clergy = client.get("/api/v1/parish/clergy", headers=member).json()
    assert clergy["parish_priest"]["name"] == "Rev. Fr. New Pastor"
    assert (
        client.get("/api/v1/parish/profile", headers=member).json()["parish_priest"] == "Rev. Fr. New Pastor"
    )
    assistant = new_priest(client, admin, "Assistant")
    client.post(
        f"/api/v1/priests/{assistant['id']}/assignments",
        headers=admin,
        json={"role": "ASSISTANT_PRIEST", "appointed_on": str(TODAY), "responsibilities": "Youth"},
    )
    assert [o["name"] for o in client.get("/api/v1/parish/clergy", headers=member).json()["others"]] == [
        "Rev. Fr. Assistant"
    ]
    serving = client.get("/api/v1/priests?serving=true", headers=admin).json()
    assert {p["full_name"] for p in serving["items"]} >= {"New Pastor", "Assistant"}
    assert "Old Pastor" not in {p["full_name"] for p in serving["items"]}

    bad = client.post(
        f"/api/v1/priests/{assistant['id']}/assignments",
        headers=admin,
        json={"role": "DEACON", "appointed_on": str(TODAY), "relieved_on": str(TODAY - timedelta(days=1))},
    )
    assert bad.status_code == 422


def test_parish_priest_role_follows_assignment(client: TestClient, tenant: TenantDescriptor) -> None:
    admin = login(client, make_user(tenant, "PARISH_ADMIN"))
    fr_user = make_user(tenant)
    priest = new_priest(client, admin, "Linked Pastor")
    r = client.post(
        f"/api/v1/priests/{priest['id']}/user", headers=admin, json={"user_id": fr_user.public_id}
    )
    assert r.status_code == 200 and r.json()["user"]["username"] == fr_user.username
    assert roles_of(tenant, fr_user) == set()  # no assignment yet

    # Same-day handover from the parish priest of earlier tests (relieve_current).
    r = client.post(
        f"/api/v1/priests/{priest['id']}/assignments",
        headers=admin,
        json={"role": "PARISH_PRIEST", "appointed_on": str(TODAY), "relieve_current": True},
    )
    assert r.status_code == 201, r.text
    assignment = r.json()["assignments"][0]
    assert assignment["grants_role"] is True and roles_of(tenant, fr_user) == {"PARISH_PRIEST"}
    me = client.get("/api/v1/auth/me", headers=login(client, fr_user)).json()
    assert "finance.approve" in me["permissions"]

    client.post(
        f"/api/v1/priests/{priest['id']}/assignments/{assignment['id']}/relieve",
        headers=admin,
        json={"reason": "Transferred"},
    )
    assert roles_of(tenant, fr_user) == set()

    # Linking a user after the appointment grants the role; unlinking removes it.
    other = new_priest(client, admin, "Later Linked")
    r = client.post(
        f"/api/v1/priests/{other['id']}/assignments",
        headers=admin,
        json={"role": "PARISH_PRIEST", "appointed_on": str(TODAY), "relieve_current": True},
    )
    assert r.status_code == 201, r.text
    u2 = make_user(tenant)
    client.post(f"/api/v1/priests/{other['id']}/user", headers=admin, json={"user_id": u2.public_id})
    assert roles_of(tenant, u2) == {"PARISH_PRIEST"}
    taken = client.post(f"/api/v1/priests/{priest['id']}/user", headers=admin, json={"user_id": u2.public_id})
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "USER_ALREADY_LINKED"
    client.post(f"/api/v1/priests/{other['id']}/user", headers=admin, json={"user_id": None})
    assert roles_of(tenant, u2) == set()

    # Retirement relieves current assignments.
    client.post(f"/api/v1/priests/{other['id']}/user", headers=admin, json={"user_id": u2.public_id})
    r = client.post(f"/api/v1/priests/{other['id']}/status", headers=admin, json={"status": "RETIRED"})
    assert r.json()["status"] == "RETIRED" and r.json()["assignments"][0]["relieved_on"] == str(TODAY)
    assert roles_of(tenant, u2) == set()
    again = client.post(
        f"/api/v1/priests/{other['id']}/assignments",
        headers=admin,
        json={"role": "ASSISTANT_PRIEST", "appointed_on": str(TODAY)},
    )
    assert again.status_code == 409


def test_link_user_requires_assign_role(client: TestClient, tenant: TenantDescriptor) -> None:
    # A custom role with priest.update but without user.assign_role cannot link accounts.
    with tenant_session_scope(tenant) as s:
        from sqlalchemy import select

        from app.modules.rbac.models import Permission, Role

        role = Role(code="PRIEST_CLERK", name="Priest clerk", scope_type="PARISH")
        role.permissions = list(s.scalars(select(Permission).where(Permission.module == "priest")))
        s.add(role)
    h = login(client, make_user(tenant, "PRIEST_CLERK"))
    p = new_priest(client, h, "Clerk Created")
    r = client.post(f"/api/v1/priests/{p['id']}/user", headers=h, json={"user_id": None})
    assert r.status_code == 403


def test_future_handover_keeps_role_until_last_day(client: TestClient, tenant: TenantDescriptor) -> None:
    from sqlalchemy import select

    from app.modules.rbac.models import UserRoleAssignment

    admin = login(client, make_user(tenant, "PARISH_ADMIN"))
    u = make_user(tenant)
    p = new_priest(client, admin, "Fixed Term Pastor")
    client.post(f"/api/v1/priests/{p['id']}/user", headers=admin, json={"user_id": u.public_id})
    handover = TODAY + timedelta(days=30)
    r = client.post(
        f"/api/v1/priests/{p['id']}/assignments",
        headers=admin,
        json={
            "role": "PARISH_PRIEST",
            "appointed_on": str(TODAY),
            "relieved_on": str(handover),
            "relieve_current": True,
        },
    )
    assert r.status_code == 201, r.text
    assert roles_of(tenant, u) == {"PARISH_PRIEST"}
    with tenant_session_scope(tenant) as s:
        ra = s.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == u.id)).one()
        assert ra.valid_to == handover - timedelta(days=1) and ra.ended_at is None
    zero = client.post(
        f"/api/v1/priests/{p['id']}/assignments",
        headers=admin,
        json={"role": "DEACON", "appointed_on": str(TODAY), "relieved_on": str(TODAY)},
    )
    assert zero.status_code == 422

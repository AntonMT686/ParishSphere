"""RBAC & user administration tests (T4). Uses a dedicated parish so admin counts are deterministic."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.common.email import OUTBOX
from app.common.ratelimit import counter
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.core.models import AuditLog
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.rbac.catalog import ADMIN_LOCKED_PERMISSIONS, ALL_PERMISSIONS, SYSTEM_ROLES
from app.modules.rbac.models import Permission, Role, UserRoleAssignment
from app.modules.rbac.service import PermissionScope, assign_role, effective_permissions, role_by_code
from app.tenancy.seed import run_seeders
from tests.conftest import auth

HOST = {"Host": "rbac.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="RBAC", name="RBAC Test Parish"))
        s.commit()
    return provision_parish("RBAC")


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    counter().reset()
    OUTBOX.clear()
    yield


def make_user(tenant: TenantDescriptor, *roles: str, org_unit_id: int | None = None, **kw: object) -> str:
    username = f"u{next(_n)}"
    with tenant_session_scope(tenant) as s:
        u = create_user(
            s,
            username=username,
            full_name=username.upper(),
            password=PW,
            must_change_password=False,
            email=kw.get("email"),
        )  # type: ignore[arg-type]
        for code in roles:
            role = role_by_code(s, code)
            assert role is not None, code
            assign_role(s, u, role, org_unit_id=org_unit_id if role.scope_type != "PARISH" else None)
    return username


def token(client: TestClient, username: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": PW}, headers=HOST)
    assert r.status_code == 200, r.text
    return {**HOST, **auth(r.json()["access_token"])}


@pytest.fixture(scope="module")
def admin(tenant: TenantDescriptor) -> str:
    return make_user(tenant, "PARISH_ADMIN")


def user_id(client: TestClient, h: dict[str, str], username: str) -> str:
    r = client.get(f"/api/v1/users?q={username}", headers=h)
    return next(u["id"] for u in r.json()["items"] if u["username"] == username)


# ----------------------------------------------------------------------------- seeding
def test_catalog_and_system_roles_seeded(tenant: TenantDescriptor) -> None:
    with tenant_session_scope(tenant) as s:
        assert s.scalar(select(func.count()).select_from(Permission)) == len(ALL_PERMISSIONS)
        codes = set(s.scalars(select(Role.code).where(Role.is_system.is_(True))))
        assert codes == {r.code for r in SYSTEM_ROLES} and len(codes) == 15
        admin_role = role_by_code(s, "PARISH_ADMIN")
        assert admin_role and {p.code for p in admin_role.permissions} >= ADMIN_LOCKED_PERMISSIONS


def test_reseeding_is_idempotent_and_keeps_customisations(tenant: TenantDescriptor) -> None:
    with tenant_session_scope(tenant) as s:
        sec = role_by_code(s, "PARISH_SECRETARY")
        assert sec
        sec.permissions = [p for p in sec.permissions if p.code != "family.delete"]
    with tenant_session_scope(tenant) as s:
        run_seeders(s, {"parish_name": tenant.name, "parish_code": tenant.code})
    with tenant_session_scope(tenant) as s:
        assert s.scalar(select(func.count()).select_from(Permission)) == len(ALL_PERMISSIONS)
        sec = role_by_code(s, "PARISH_SECRETARY")
        assert sec and "family.delete" not in {p.code for p in sec.permissions}


def test_new_catalog_permission_granted_to_system_roles(
    tenant: TenantDescriptor, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.rbac import catalog, service

    new_catalog = {**catalog.PERMISSION_CATALOG, "festival": {"view": "View festivals"}}
    priest = next(r for r in catalog.SYSTEM_ROLES if r.code == "PARISH_PRIEST")
    patched_roles = tuple(
        type(r)(r.code, r.name, r.scope_type, r.description, r.permissions | {"festival.view"})
        if r is priest
        else r
        for r in catalog.SYSTEM_ROLES
    )
    monkeypatch.setattr(service, "PERMISSION_CATALOG", new_catalog)
    monkeypatch.setattr(service, "SYSTEM_ROLES", patched_roles)
    with tenant_session_scope(tenant) as s:
        service.seed_rbac(s, {})
    with tenant_session_scope(tenant) as s:
        priest_role = role_by_code(s, "PARISH_PRIEST")
        sec = role_by_code(s, "PARISH_SECRETARY")
        assert priest_role and "festival.view" in {p.code for p in priest_role.permissions}
        assert sec and "festival.view" not in {p.code for p in sec.permissions}
        # cleanup so other tests see the real catalog
        perm = s.scalars(select(Permission).where(Permission.code == "festival.view")).one()
        priest_role.permissions.remove(perm)
        s.flush()
        s.delete(perm)


# ----------------------------------------------------------------------------- effective permissions
def test_me_lists_roles_and_permissions(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    me = client.get("/api/v1/auth/me", headers=token(client, admin)).json()
    assert me["roles"] == ["PARISH_ADMIN"]
    assert "user.create" in me["permissions"] and "finance.approve" not in me["permissions"]


def test_login_response_includes_permissions(client: TestClient, tenant: TenantDescriptor) -> None:
    u = make_user(tenant, "PARISH_TREASURER")
    r = client.post("/api/v1/auth/login", json={"username": u, "password": PW}, headers=HOST)
    assert "finance.create" in r.json()["user"]["permissions"]


def test_org_unit_scoped_permissions(tenant: TenantDescriptor) -> None:
    u = make_user(tenant, "COMMITTEE_SECRETARY", org_unit_id=501)
    with tenant_session_scope(tenant) as s:
        user = s.scalars(select(User).where(User.username == u)).one()
        eff = effective_permissions(s, user)
        assert eff.has("activity.create", 501)
        assert not eff.has("activity.create", 502)
        assert not eff.has("activity.create", None)  # parish-level records need a parish-wide grant
        assert eff.has("activity.create", anywhere=True)
        assert not eff.has("finance.approve", anywhere=True)
        scope = eff.scope("activity.view")
        assert scope.org_unit_ids == {501} and not scope.parish_wide


def test_assignment_validity_window(tenant: TenantDescriptor) -> None:
    u = make_user(tenant)
    with tenant_session_scope(tenant) as s:
        user = s.scalars(select(User).where(User.username == u)).one()
        treasurer, secretary = role_by_code(s, "PARISH_TREASURER"), role_by_code(s, "PARISH_SECRETARY")
        assert treasurer and secretary
        assign_role(s, user, treasurer, valid_from=date.today() + timedelta(days=3))
        a = assign_role(s, user, secretary, valid_from=date.today() - timedelta(days=30))
        a.valid_to = date.today() - timedelta(days=1)
        s.flush()
        eff = effective_permissions(s, user)
        assert eff.role_codes == set()
        assert effective_permissions(s, user, date.today() + timedelta(days=3)).role_codes == {
            "PARISH_TREASURER"
        }


def test_permission_scope_filter() -> None:
    from sqlalchemy import column

    col = column("org_unit_id")
    assert str(PermissionScope("x", parish_wide=True).filter(col)) == "true"
    assert str(PermissionScope("x").filter(col)) == "false"
    assert "IN" in str(PermissionScope("x", org_unit_ids=frozenset({1, 2})).filter(col))


# ----------------------------------------------------------------------------- authorization
def test_users_api_requires_permission(client: TestClient, tenant: TenantDescriptor) -> None:
    for role in ("PARISH_TREASURER", "GENERAL_MEMBER"):
        h = token(client, make_user(tenant, role))
        r = client.get("/api/v1/users", headers=h)
        assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED"
    h = token(client, make_user(tenant))  # no roles at all
    assert client.get("/api/v1/roles", headers=h).status_code == 403


def test_org_scoped_holder_cannot_use_parish_wide_admin_endpoint(
    client: TestClient, tenant: TenantDescriptor
) -> None:
    with tenant_session_scope(tenant) as s:
        role = Role(code="ORG_USER_ADMIN", name="Org user admin", scope_type="ANY")
        role.permissions = list(s.scalars(select(Permission).where(Permission.code == "user.view")))
        s.add(role)
    u = make_user(tenant, "ORG_USER_ADMIN", org_unit_id=77)
    assert client.get("/api/v1/users", headers=token(client, u)).status_code == 403


def test_priest_cannot_manage_roles(client: TestClient, tenant: TenantDescriptor) -> None:
    h = token(client, make_user(tenant, "PARISH_PRIEST"))
    assert client.get("/api/v1/roles", headers=h).status_code == 200
    r = client.post("/api/v1/roles", json={"code": "X1", "name": "X one"}, headers=h)
    assert r.status_code == 403


# ----------------------------------------------------------------------------- users API
def test_user_crud_and_role_assignment(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    h = token(client, admin)
    r = client.post(
        "/api/v1/users",
        json={
            "username": "Treasurer.One",
            "full_name": "Mr Treasurer",
            "email": "treasurer@rbac.org",
            "password": "Denarius-2026!",
            "role_codes": ["parish_treasurer"],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    u = r.json()
    assert (
        u["username"] == "treasurer.one" and u["roles"] == ["PARISH_TREASURER"] and u["must_change_password"]
    )

    dup = client.post(
        "/api/v1/users", json={"username": "treasurer.one", "full_name": "Dup", "password": PW}, headers=h
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "USERNAME_EXISTS"

    r = client.get("/api/v1/users?role=PARISH_TREASURER&sort=-created_at", headers=h)
    assert any(x["id"] == u["id"] for x in r.json()["items"])

    r = client.patch(
        f"/api/v1/users/{u['id']}", json={"full_name": "Mr. T", "preferred_language": "ta"}, headers=h
    )
    assert r.json()["full_name"] == "Mr. T" and r.json()["preferred_language"] == "ta"

    r = client.post(f"/api/v1/users/{u['id']}/roles", json={"role_code": "REVIEWER"}, headers=h)
    assert r.status_code == 201 and r.json()["active"] is True
    assignment = r.json()["id"]
    again = client.post(f"/api/v1/users/{u['id']}/roles", json={"role_code": "REVIEWER"}, headers=h)
    assert again.status_code == 409 and again.json()["error"]["code"] == "ROLE_ALREADY_ASSIGNED"

    assert client.delete(f"/api/v1/users/{u['id']}/roles/{assignment}", headers=h).status_code == 204
    roles = client.get(f"/api/v1/users/{u['id']}/roles", headers=h).json()
    assert [x["role_code"] for x in roles] == ["PARISH_TREASURER"]
    history = client.get(f"/api/v1/users/{u['id']}/roles?include_history=true", headers=h).json()
    assert {x["role_code"] for x in history} == {"PARISH_TREASURER", "REVIEWER"}

    with tenant_session_scope(tenant) as s:
        actions = set(s.scalars(select(AuditLog.action).where(AuditLog.entity_id == u["id"])))
    assert {"CREATE", "UPDATE", "ROLE_ASSIGNED", "ROLE_REMOVED"} <= actions


def test_create_user_with_invite(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    h = token(client, admin)
    r = client.post(
        "/api/v1/users",
        json={"username": "invitee", "full_name": "Invitee", "email": "inv@rbac.org"},
        headers=h,
    )
    assert r.status_code == 201
    assert len(OUTBOX) == 1 and "set your password" in OUTBOX[0].get_content()
    bad = client.post("/api/v1/users", json={"username": "nobody", "full_name": "Nobody"}, headers=h)
    assert bad.status_code == 422


def test_scope_type_validation(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    h = token(client, admin)
    uid = user_id(client, h, make_user(tenant))
    r = client.post(f"/api/v1/users/{uid}/roles", json={"role_code": "COMMITTEE_SECRETARY"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "org_unit_id"
    r = client.post(
        f"/api/v1/users/{uid}/roles", json={"role_code": "COMMITTEE_SECRETARY", "org_unit_id": "X"}, headers=h
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "ORG_UNITS_NOT_AVAILABLE"
    r = client.post(f"/api/v1/users/{uid}/roles", json={"role_code": "NOPE"}, headers=h)
    assert r.status_code == 422


def test_cannot_modify_self(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    h = token(client, admin)
    me = user_id(client, h, admin)
    for method, path in [
        ("post", f"/api/v1/users/{me}/deactivate"),
        ("delete", f"/api/v1/users/{me}"),
        ("post", f"/api/v1/users/{me}/roles"),
    ]:
        r = client.request(
            method, path, headers=h, json={"role_code": "APPROVER"} if path.endswith("roles") else None
        )
        assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_MODIFICATION"


def test_deactivate_revokes_sessions_and_blocks_login(
    client: TestClient, tenant: TenantDescriptor, admin: str
) -> None:
    h = token(client, admin)
    victim = make_user(tenant, "PARISH_SECRETARY")
    vh = token(client, victim)
    vid = user_id(client, h, victim)
    assert client.post(f"/api/v1/users/{vid}/deactivate", headers=h).json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=vh).status_code == 401
    assert (
        client.post("/api/v1/auth/login", json={"username": victim, "password": PW}, headers=HOST).status_code
        == 401
    )
    assert client.post(f"/api/v1/users/{vid}/activate", headers=h).json()["is_active"] is True
    assert (
        client.post("/api/v1/auth/login", json={"username": victim, "password": PW}, headers=HOST).status_code
        == 200
    )


def test_unlock_and_admin_reset(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    h = token(client, admin)
    victim = make_user(tenant, email="victim@rbac.org")
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": victim, "password": "bad"}, headers=HOST)
    vid = user_id(client, h, victim)
    assert client.get(f"/api/v1/users/{vid}", headers=h).json()["is_locked"] is True
    assert client.post(f"/api/v1/users/{vid}/unlock", headers=h).json()["is_locked"] is False
    counter().reset()
    assert (
        client.post("/api/v1/auth/login", json={"username": victim, "password": PW}, headers=HOST).status_code
        == 200
    )
    assert client.post(f"/api/v1/users/{vid}/send-password-reset", headers=h).status_code == 202
    assert OUTBOX and OUTBOX[-1]["To"] == "victim@rbac.org"


def test_last_admin_protection(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    # A user manager without the admin role (custom role) tries to remove the only administrator.
    with tenant_session_scope(tenant) as s:
        role = Role(code="USER_MANAGER", name="User manager", scope_type="PARISH")
        role.permissions = list(s.scalars(select(Permission).where(Permission.module == "user")))
        s.add(role)
    mgr = token(client, make_user(tenant, "USER_MANAGER"))
    with tenant_session_scope(tenant) as s:
        admins = set(
            s.scalars(
                select(User.username)
                .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
                .join(Role)
                .where(Role.code == "PARISH_ADMIN", UserRoleAssignment.ended_at.is_(None))
            )
        )
    assert admins == {admin}
    aid = user_id(client, mgr, admin)
    r = client.post(f"/api/v1/users/{aid}/deactivate", headers=mgr)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAST_ADMIN"
    assert client.delete(f"/api/v1/users/{aid}", headers=mgr).status_code == 409
    assignment = client.get(f"/api/v1/users/{aid}/roles", headers=mgr).json()[0]["id"]
    assert client.delete(f"/api/v1/users/{aid}/roles/{assignment}", headers=mgr).status_code == 409

    # With a second administrator the first can be deactivated.
    second = make_user(tenant, "PARISH_ADMIN")
    assert client.post(f"/api/v1/users/{aid}/deactivate", headers=mgr).status_code == 200
    assert client.post(f"/api/v1/users/{aid}/activate", headers=token(client, second)).status_code == 200


def test_delete_user_archives_and_ends_roles(
    client: TestClient, tenant: TenantDescriptor, admin: str
) -> None:
    h = token(client, admin)
    gone = make_user(tenant, "PARISH_SECRETARY")
    gid = user_id(client, h, gone)
    assert client.delete(f"/api/v1/users/{gid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/users/{gid}", headers=h).status_code == 404
    with tenant_session_scope(tenant) as s:
        u = s.scalars(select(User).where(User.public_id == gid)).one()
        assert u.is_deleted and not u.is_active
        assert all(
            a.ended_at
            for a in s.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == u.id))
        )


# ----------------------------------------------------------------------------- roles API
def test_role_management(client: TestClient, tenant: TenantDescriptor, admin: str) -> None:
    h = token(client, admin)
    perms = client.get("/api/v1/permissions", headers=h).json()
    assert {m["module"] for m in perms} >= {"family", "finance", "workflow"}

    r = client.post(
        "/api/v1/roles",
        json={
            "code": "choir_master",
            "name": "Choir Master",
            "scope_type": "ORG_UNIT",
            "permissions": ["activity.view", "activity.create"],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    role = r.json()
    assert role["code"] == "CHOIR_MASTER" and role["permission_count"] == 2 and not role["is_system"]

    bad = client.post(
        "/api/v1/roles", json={"code": "BAD", "name": "Bad", "permissions": ["nope.view"]}, headers=h
    )
    assert bad.status_code == 422

    r = client.patch(f"/api/v1/roles/{role['id']}", json={"permissions": ["activity.view"]}, headers=h)
    assert r.json()["permissions"] == ["activity.view"]

    roles = {x["code"]: x for x in client.get("/api/v1/roles", headers=h).json()}
    admin_role = roles["PARISH_ADMIN"]
    assert admin_role["active_users"] >= 1
    r = client.patch(f"/api/v1/roles/{admin_role['id']}", json={"permissions": ["user.view"]}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ADMIN_PERMISSIONS_LOCKED"

    assert client.delete(f"/api/v1/roles/{roles['PARISH_PRIEST']['id']}", headers=h).status_code == 409
    r = client.post("/api/v1/roles", json={"code": "TEMP_ROLE", "name": "Temp"}, headers=h)
    temp = r.json()
    holder = user_id(client, h, make_user(tenant, "TEMP_ROLE"))
    r = client.delete(f"/api/v1/roles/{temp['id']}", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ROLE_IN_USE"
    assert holder
    assert client.delete(f"/api/v1/roles/{role['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/roles/{role['id']}", headers=h).status_code == 404

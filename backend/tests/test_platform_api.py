"""Platform console API tests: auth, dioceses, parishes, suspension."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth


def test_health(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200 and r.json()["checks"]["master_db"] == "ok"
    assert "X-Request-ID" in r.headers


def test_login_failure_and_error_envelope(client: TestClient) -> None:
    r = client.post(
        "/api/v1/platform/auth/login", json={"email": "root@parishsphere.org", "password": "wrong"}
    )
    assert r.status_code == 401
    body = r.json()["error"]
    assert body["code"] == "INVALID_CREDENTIALS" and body["trace_id"]


def test_validation_error_envelope(client: TestClient) -> None:
    r = client.post("/api/v1/platform/auth/login", json={"email": "not-an-email"})
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"email", "password"} <= fields


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/platform/dioceses").status_code == 401


def test_me(client: TestClient, super_token: str) -> None:
    r = client.get("/api/v1/platform/auth/me", headers=auth(super_token))
    assert r.status_code == 200 and r.json()["is_super_admin"] is True


def test_diocese_crud(client: TestClient, super_token: str) -> None:
    r = client.post(
        "/api/v1/platform/dioceses",
        json={"code": "tvl", "name": "Tirunelveli Diocese", "city": "Tirunelveli"},
        headers=auth(super_token),
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["code"] == "TVL" and len(d["id"]) == 26
    dup = client.post(
        "/api/v1/platform/dioceses", json={"code": "TVL", "name": "x y"}, headers=auth(super_token)
    )
    assert dup.status_code == 409
    r = client.patch(
        f"/api/v1/platform/dioceses/{d['id']}", json={"bishop_name": "Most Rev. A"}, headers=auth(super_token)
    )
    assert r.json()["bishop_name"] == "Most Rev. A"
    r = client.get("/api/v1/platform/dioceses?q=tirunel&sort=-name", headers=auth(super_token))
    assert r.json()["total"] == 1
    bad = client.get("/api/v1/platform/dioceses?sort=password", headers=auth(super_token))
    assert bad.status_code == 422


def test_non_super_admin_cannot_write_and_sees_only_scoped(client: TestClient) -> None:
    tok = client.post(
        "/api/v1/platform/auth/login", json={"email": "viewer@parishsphere.org", "password": "Vi3wer-secret!"}
    ).json()["access_token"]
    r = client.post("/api/v1/platform/dioceses", json={"code": "XX", "name": "Nope"}, headers=auth(tok))
    assert r.status_code == 403
    r = client.get("/api/v1/platform/dioceses", headers=auth(tok))
    assert r.json()["total"] == 0  # no diocese scopes assigned


def test_create_parish_via_api_and_suspend(client: TestClient, super_token: str) -> None:
    r = client.post(
        "/api/v1/platform/parishes",
        json={"diocese_code": "CHN", "code": "olv", "name": "Our Lady of Velankanni", "subdomain": "olv"},
        headers=auth(super_token),
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "ACTIVE" and p["code"] == "OLV" and p["schema_version"]

    assert client.get("/api/v1/tenant/branding", headers={"Host": "olv.parishsphere.test"}).status_code == 200
    r = client.patch(
        f"/api/v1/platform/parishes/{p['id']}/status", json={"status": "SUSPENDED"}, headers=auth(super_token)
    )
    assert r.status_code == 200
    r = client.get("/api/v1/tenant/branding", headers={"Host": "olv.parishsphere.test"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "TENANT_SUSPENDED"

    r = client.post(
        "/api/v1/platform/parishes",
        json={"diocese_code": "CHN", "code": "OLV", "name": "Again"},
        headers=auth(super_token),
    )
    assert r.status_code == 409


def test_parish_validation(client: TestClient, super_token: str) -> None:
    r = client.post(
        "/api/v1/platform/parishes",
        json={"diocese_code": "CHN", "code": "ABC", "name": "Reserved", "subdomain": "www"},
        headers=auth(super_token),
    )
    assert r.status_code == 422
    r = client.post(
        "/api/v1/platform/parishes",
        json={"diocese_code": "ZZZ", "code": "ABC", "name": "No diocese"},
        headers=auth(super_token),
    )
    assert r.status_code == 404


def test_platform_token_rejected_for_wrong_type(client: TestClient) -> None:
    from app.core.security import create_access_token

    tok = create_access_token(subject="x", token_type="tenant", tenant_id="t")
    assert client.get("/api/v1/platform/auth/me", headers=auth(tok)).status_code == 401


def test_lockout_after_repeated_failures(client: TestClient) -> None:
    from app.db.master import master_session
    from app.master.auth import create_platform_user

    with master_session() as s:
        create_platform_user(s, email="lock@parishsphere.org", full_name="Lock", password="L0ck-secret!!")
        s.commit()
    for _ in range(5):
        client.post("/api/v1/platform/auth/login", json={"email": "lock@parishsphere.org", "password": "bad"})
    r = client.post(
        "/api/v1/platform/auth/login", json={"email": "lock@parishsphere.org", "password": "L0ck-secret!!"}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"

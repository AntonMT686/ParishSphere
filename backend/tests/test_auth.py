"""Parish authentication & session lifecycle tests (T3)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.email import OUTBOX
from app.common.ratelimit import counter
from app.core.config import get_settings
from app.db.base import utcnow
from app.db.tenant import tenant_session_scope
from app.modules.core.models import AuditLog
from app.modules.identity.models import UserSession
from app.modules.identity.passwords import password_problems
from app.modules.identity.service import create_user
from app.tenancy.resolver import resolve_tenant
from tests.conftest import auth

STM = {"Host": "stmarys.parishsphere.test"}
HCR = {"Host": "holycross.parishsphere.test"}
PASSWORD = "Gl0ria-in-Excelsis"
_seq = count(1)


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    counter().reset()
    OUTBOX.clear()
    yield
    counter().reset()


@pytest.fixture()
def user(two_parishes: tuple[str, str]) -> dict[str, str]:
    """A fresh active user in STMARYS (unique per test so lockouts never leak between tests)."""
    n = next(_seq)
    username, email = f"secretary{n}", f"secretary{n}@stmarys.org"
    tenant = resolve_tenant(code="STMARYS")
    assert tenant
    with tenant_session_scope(tenant) as s:
        create_user(
            s,
            username=username,
            full_name=f"Secretary {n}",
            email=email,
            password=PASSWORD,
            must_change_password=False,
        )
    return {"username": username, "email": email}


def login(client: TestClient, username: str, password: str = PASSWORD, headers: dict[str, str] = STM):
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}, headers=headers
    )


def csrf(client: TestClient) -> dict[str, str]:
    return {**STM, "X-CSRF-Token": client.cookies.get(get_settings().csrf_cookie_name) or ""}


def stm_session(public_id: str) -> Iterator[UserSession]:
    tenant = resolve_tenant(code="STMARYS")
    assert tenant
    with tenant_session_scope(tenant) as s:
        yield s.scalars(select(UserSession).where(UserSession.public_id == public_id)).one()


def sid_of(client: TestClient, token: str) -> str:
    from app.core.security import decode_access_token

    return decode_access_token(token)["sid"]


# ----------------------------------------------------------------------------- login
def test_login_success_sets_cookies_and_me(client: TestClient, user: dict[str, str]) -> None:
    r = login(client, user["username"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    assert body["idle_timeout_seconds"] == 1800
    assert body["user"]["username"] == user["username"]
    set_cookie = r.headers.get_list("set-cookie")
    refresh_cookie = next(c for c in set_cookie if c.startswith("ps_refresh="))
    assert "HttpOnly" in refresh_cookie and "Path=/api/v1/auth" in refresh_cookie
    assert "samesite=strict" in refresh_cookie.lower()
    assert any(c.startswith("ps_csrf=") and "HttpOnly" not in c for c in set_cookie)

    me = client.get("/api/v1/auth/me", headers={**STM, **auth(body["access_token"])})
    assert me.status_code == 200 and me.json()["email"] == user["email"]


def test_login_by_email_case_insensitive(client: TestClient, user: dict[str, str]) -> None:
    assert login(client, user["email"].upper()).status_code == 200


def test_bad_credentials_are_generic_and_audited(client: TestClient, user: dict[str, str]) -> None:
    r1 = login(client, user["username"], "wrong-password")
    r2 = login(client, "no-such-user", "wrong-password")
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["error"]["code"] == r2.json()["error"]["code"] == "INVALID_CREDENTIALS"
    tenant = resolve_tenant(code="STMARYS")
    assert tenant
    with tenant_session_scope(tenant) as s:
        actions = s.scalars(select(AuditLog.action).where(AuditLog.action == "LOGIN_FAILED")).all()
    assert len(actions) >= 2


def test_account_lockout(client: TestClient, user: dict[str, str]) -> None:
    for _ in range(5):
        assert login(client, user["username"], "wrong-password").status_code == 401
    r = login(client, user["username"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_ip_rate_limit(client: TestClient, user: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "max_failed_logins_per_ip", 3)
    for i in range(3):
        login(client, f"ghost{i}", "x")
    r = login(client, user["username"])
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"


def test_inactive_user_cannot_login(client: TestClient, user: dict[str, str]) -> None:
    from app.modules.identity.models import User

    tenant = resolve_tenant(code="STMARYS")
    assert tenant
    with tenant_session_scope(tenant) as s:
        s.scalars(select(User).where(User.username == user["username"])).one().is_active = False
    assert login(client, user["username"]).status_code == 401


# ----------------------------------------------------------------------------- token binding
def test_token_is_bound_to_its_parish(client: TestClient, user: dict[str, str]) -> None:
    token = login(client, user["username"]).json()["access_token"]
    r = client.get("/api/v1/auth/me", headers={**HCR, **auth(token)})
    assert r.status_code == 403 and r.json()["error"]["code"] == "TENANT_MISMATCH"


def test_platform_token_rejected_on_parish_routes(client: TestClient, super_token: str) -> None:
    r = client.get("/api/v1/auth/me", headers={**STM, **auth(super_token)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN_TYPE"


def test_missing_and_garbage_tokens(client: TestClient, two_parishes: tuple[str, str]) -> None:
    assert client.get("/api/v1/auth/me", headers=STM).status_code == 401
    r = client.get("/api/v1/auth/me", headers={**STM, **auth("not.a.jwt")})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_TOKEN"


# ----------------------------------------------------------------------------- refresh
def test_refresh_rotates_and_detects_reuse(client: TestClient, user: dict[str, str]) -> None:
    first = login(client, user["username"]).json()
    old_refresh = client.cookies.get("ps_refresh")
    r = client.post("/api/v1/auth/refresh", headers=csrf(client))
    assert r.status_code == 200, r.text
    new_access = r.json()["access_token"]
    assert new_access != first["access_token"]
    assert client.cookies.get("ps_refresh") != old_refresh

    # Replaying the old refresh token (stolen copy) kills the session.
    client.cookies.set("ps_refresh", old_refresh or "", path="/api/v1/auth")
    r = client.post("/api/v1/auth/refresh", headers=csrf(client))
    assert r.status_code == 401 and r.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"
    r = client.get("/api/v1/auth/me", headers={**STM, **auth(new_access)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_REVOKED"


def test_refresh_requires_csrf(client: TestClient, user: dict[str, str]) -> None:
    login(client, user["username"])
    r = client.post("/api/v1/auth/refresh", headers={**STM, "X-CSRF-Token": "forged"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    assert client.post("/api/v1/auth/refresh", headers=STM).status_code == 403


def test_refresh_without_cookie(client: TestClient, two_parishes: tuple[str, str]) -> None:
    client.cookies.set("ps_csrf", "abc")
    r = client.post("/api/v1/auth/refresh", headers={**STM, "X-CSRF-Token": "abc"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


# ----------------------------------------------------------------------------- idle timeout
def _age_session(sid: str, minutes: int) -> None:
    for sess in stm_session(sid):
        sess.last_activity_at = utcnow() - timedelta(minutes=minutes)


def test_idle_timeout_expires_session(client: TestClient, user: dict[str, str]) -> None:
    token = login(client, user["username"]).json()["access_token"]
    sid = sid_of(client, token)
    _age_session(sid, 31)
    r = client.get("/api/v1/auth/me", headers={**STM, **auth(token)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_EXPIRED"
    for sess in stm_session(sid):
        assert sess.revoke_reason == "IDLE_TIMEOUT"  # revocation persisted
    # Refresh cannot resurrect an idle session either.
    assert client.post("/api/v1/auth/refresh", headers=csrf(client)).status_code == 401


def test_activity_within_timeout_keeps_session_alive(client: TestClient, user: dict[str, str]) -> None:
    token = login(client, user["username"]).json()["access_token"]
    sid = sid_of(client, token)
    _age_session(sid, 29)
    assert client.get("/api/v1/auth/me", headers={**STM, **auth(token)}).status_code == 200
    for sess in stm_session(sid):
        assert utcnow() - sess.last_activity_at < timedelta(minutes=1)  # touched


def test_refresh_extends_idle_window(client: TestClient, user: dict[str, str]) -> None:
    token = login(client, user["username"]).json()["access_token"]
    sid = sid_of(client, token)
    _age_session(sid, 28)  # the "session expires in 2 minutes – continue?" moment
    assert client.post("/api/v1/auth/refresh", headers=csrf(client)).status_code == 200
    for sess in stm_session(sid):
        assert utcnow() - sess.last_activity_at < timedelta(minutes=1)


# ----------------------------------------------------------------------------- logout
def test_logout_revokes_session_and_clears_cookies(client: TestClient, user: dict[str, str]) -> None:
    token = login(client, user["username"]).json()["access_token"]
    r = client.post("/api/v1/auth/logout", headers=csrf(client))
    assert r.status_code == 204
    assert any(c.startswith('ps_refresh=""') or "Max-Age=0" in c for c in r.headers.get_list("set-cookie"))
    r = client.get("/api/v1/auth/me", headers={**STM, **auth(token)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_REVOKED"


def test_logout_all(client: TestClient, user: dict[str, str]) -> None:
    other = TestClient(client.app)
    t1 = login(client, user["username"]).json()["access_token"]
    t2 = login(other, user["username"]).json()["access_token"]
    sessions = client.get("/api/v1/auth/sessions", headers={**STM, **auth(t1)}).json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    assert client.post("/api/v1/auth/logout-all", headers={**STM, **auth(t1)}).status_code == 204
    assert other.get("/api/v1/auth/me", headers={**STM, **auth(t2)}).status_code == 401


def test_revoke_specific_session(client: TestClient, user: dict[str, str]) -> None:
    other = TestClient(client.app)
    t1 = login(client, user["username"]).json()["access_token"]
    t2 = login(other, user["username"]).json()["access_token"]
    sid2 = sid_of(other, t2)
    assert client.delete(f"/api/v1/auth/sessions/{sid2}", headers={**STM, **auth(t1)}).status_code == 204
    assert other.get("/api/v1/auth/me", headers={**STM, **auth(t2)}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={**STM, **auth(t1)}).status_code == 200
    assert (
        client.delete(
            "/api/v1/auth/sessions/01HZZZZZZZZZZZZZZZZZZZZZZZ", headers={**STM, **auth(t1)}
        ).status_code
        == 404
    )


# ----------------------------------------------------------------------------- passwords
def test_change_password(client: TestClient, user: dict[str, str]) -> None:
    other = TestClient(client.app)
    token = login(client, user["username"]).json()["access_token"]
    other_token = login(other, user["username"]).json()["access_token"]
    h = {**STM, **auth(token)}
    r = client.post(
        "/api/v1/auth/password/change", json={"current_password": "nope", "new_password": "x"}, headers=h
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"
    r = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=h,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"
    r = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "Ave-Maria-2026"},
        headers=h,
    )
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200  # current session kept
    assert other.get("/api/v1/auth/me", headers={**STM, **auth(other_token)}).status_code == 401
    assert login(client, user["username"], "Ave-Maria-2026").status_code == 200


def test_forgot_and_reset_password(client: TestClient, user: dict[str, str]) -> None:
    token = login(client, user["username"]).json()["access_token"]
    r = client.post("/api/v1/auth/password/forgot", json={"username": user["email"]}, headers=STM)
    assert r.status_code == 202
    unknown = client.post("/api/v1/auth/password/forgot", json={"username": "nobody"}, headers=STM)
    assert unknown.status_code == 202 and unknown.json() == r.json()  # no enumeration
    assert len(OUTBOX) == 1
    body = OUTBOX[0].get_content()
    assert "http://stmarys.parishsphere.localhost/reset-password?token=" in body
    reset_token = re.search(r"token=([\w-]+)", body).group(1)  # type: ignore[union-attr]

    weak = client.post(
        "/api/v1/auth/password/reset", json={"token": reset_token, "new_password": "weak"}, headers=STM
    )
    assert weak.status_code == 422
    ok = client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": "Sanctus-Dominus-7"},
        headers=STM,
    )
    assert ok.status_code == 200
    again = client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": "Sanctus-Dominus-8"},
        headers=STM,
    )
    assert again.status_code == 422 and again.json()["error"]["code"] == "INVALID_RESET_TOKEN"
    assert (
        client.get("/api/v1/auth/me", headers={**STM, **auth(token)}).status_code == 401
    )  # sessions revoked
    assert login(client, user["username"], "Sanctus-Dominus-7").status_code == 200


def test_reset_token_from_other_parish_is_useless(client: TestClient, user: dict[str, str]) -> None:
    client.post("/api/v1/auth/password/forgot", json={"username": user["username"]}, headers=STM)
    reset_token = re.search(r"token=([\w-]+)", OUTBOX[0].get_content()).group(1)  # type: ignore[union-attr]
    r = client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": "Sanctus-Dominus-9"},
        headers=HCR,
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("Gl0ria-in-Excelsis", True),
        ("short1A", False),
        ("alllowercaseletters", False),
        ("password123", False),
        ("Secretary-1-pass", False),
    ],
)
def test_password_policy(password: str, ok: bool) -> None:
    assert (password_problems(password, username="secretary") == []) is ok


# ----------------------------------------------------------------------------- bootstrap
def test_create_parish_with_admin_sends_invite(client: TestClient, super_token: str) -> None:
    r = client.post(
        "/api/v1/platform/parishes",
        json={
            "diocese_code": "MDU",
            "code": "STJOSEPH",
            "name": "St. Joseph's",
            "subdomain": "stjoseph",
            "admin_username": "Admin",
            "admin_email": "office@stjoseph.org",
            "admin_full_name": "Parish Office",
        },
        headers=auth(super_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["admin_username"] == "admin"
    assert len(OUTBOX) == 1 and OUTBOX[0]["To"] == "office@stjoseph.org"
    link = re.search(r"token=([\w-]+)", OUTBOX[0].get_content()).group(1)  # type: ignore[union-attr]
    host = {"Host": "stjoseph.parishsphere.test"}
    r = client.post(
        "/api/v1/auth/password/reset", json={"token": link, "new_password": "Pax-Vobiscum-1"}, headers=host
    )
    assert r.status_code == 200
    r = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Pax-Vobiscum-1"}, headers=host
    )
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is False

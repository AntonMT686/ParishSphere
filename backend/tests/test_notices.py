"""Notices & news (T13)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.ratelimit import counter
from app.common.storage import reset_storage
from app.core.config import get_settings
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.activities.service import parish_now
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.notices import service as svc
from app.modules.notices.models import Notice
from app.modules.notifications.models import Notification
from app.modules.org_units.models import OrgUnit
from app.modules.rbac.service import assign_role, role_by_code
from tests.conftest import auth, make_org_unit

HOST = {"Host": "ntc.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="NTC", name="St. Antony's Church"))
        s.commit()
    return provision_parish("NTC")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # type: ignore[no-untyped-def]
    counter().reset()
    monkeypatch.setattr(get_settings(), "storage_local_dir", tmp_path / "files")
    reset_storage()
    yield
    reset_storage()


def make_user(tenant: TenantDescriptor, *roles: str, unit: int | None = None) -> User:
    username = f"n{next(_n)}"
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
def staff(tenant: TenantDescriptor) -> dict[str, User]:
    return {
        "secretary": make_user(tenant, "PARISH_SECRETARY"),
        "president": make_user(tenant, "PARISH_PRESIDENT"),
        "priest": make_user(tenant, "PARISH_PRIEST"),
        "member": make_user(tenant, "GENERAL_MEMBER"),
    }


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


def notified(tenant: TenantDescriptor, user: User, event: str) -> int:
    with tenant_session_scope(tenant) as s:
        return len(
            s.scalars(
                select(Notification).where(Notification.user_id == user.id, Notification.event_code == event)
            ).all()
        )


def notice(client: TestClient, h: dict[str, str], **kw: object) -> dict:
    body = {
        "title": "Christmas Mass timings",
        "body": "Midnight Mass at 11:30 pm.\nChristmas Day: 7 am and 9 am.",
        "category": "WEEKLY",
        **kw,
    }
    r = client.post("/api/v1/notices", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def board_ids(client: TestClient, user: User) -> set[str]:
    return {
        n["id"]
        for n in client.get("/api/v1/notices/board?size=100", headers=login(client, user)).json()["items"]
    }


def test_prepare_review_approve_publish(client: TestClient, tenant: TenantDescriptor, staff: dict) -> None:
    h = login(client, staff["secretary"])
    n = notice(client, h, is_important=True, title_local="கிறிஸ்துமஸ் திருப்பலி நேரங்கள்", is_public=True)
    assert n["status"] == "DRAFT" and n["state"] == "DRAFT" and n["code"].startswith("NTC-")
    assert n["id"] not in board_ids(client, staff["member"])  # drafts never reach readers
    r = client.post(f"/api/v1/notices/{n['id']}/submit", json={}, headers=h)
    assert r.json()["status"] == "IN_REVIEW"
    assert (
        client.put(
            f"/api/v1/notices/{n['id']}", json={"title": "Changed", "body": "xyz"}, headers=h
        ).status_code
        == 409
    )
    # Secretary prepared it, so the "Secretary or President" stage goes to the President; then the Priest.
    approve_all(client, staff["president"])
    assert client.get(f"/api/v1/notices/{n['id']}", headers=h).json()["status"] == "IN_REVIEW"
    approve_all(client, staff["priest"])
    got = client.get(f"/api/v1/notices/{n['id']}", headers=h).json()
    assert got["status"] == "PUBLISHED" and got["state"] == "LIVE"
    assert n["id"] in board_ids(client, staff["member"])
    assert notified(tenant, staff["member"], "notice.important") == 1  # important → important event (email)
    # Public portal: no sign-in needed.
    pub = client.get("/api/v1/public/notices", headers=HOST).json()
    assert [p["title_local"] for p in pub] == ["கிறிஸ்துமஸ் திருப்பலி நேரங்கள்"]
    pdf = client.get("/api/v1/notices/bulletin.pdf", headers=login(client, staff["member"]))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_scheduled_publication_and_expiry(client: TestClient, tenant: TenantDescriptor, staff: dict) -> None:
    h = login(client, staff["secretary"])
    with tenant_session_scope(tenant) as s:
        now = parish_now(s)
    later = now + timedelta(days=2)
    n = notice(
        client,
        h,
        title="Parish feast novena",
        category="EVENT",
        publish_at=later.isoformat(),
        expires_at=(later + timedelta(days=9)).isoformat(),
    )
    client.post(f"/api/v1/notices/{n['id']}/submit", json={}, headers=h)
    approve_all(client, staff["president"], staff["priest"])
    got = client.get(f"/api/v1/notices/{n['id']}", headers=h).json()
    assert (got["status"], got["state"]) == ("APPROVED", "SCHEDULED") and got["can"]["publish"]
    assert n["id"] not in board_ids(client, staff["member"])
    with tenant_session_scope(tenant) as s:
        assert svc.publish_due(s, tenant) == 0  # not yet
        assert svc.publish_due(s, tenant, later + timedelta(minutes=5)) == 1
    with tenant_session_scope(tenant) as s:
        row = s.scalar(select(Notice).where(Notice.public_id == n["id"]))
        assert row and row.status == "PUBLISHED" and row.published_at is not None
    assert notified(tenant, staff["member"], "notice.published") >= 1
    # Expired notices leave the board; they stay in the manage list.
    with tenant_session_scope(tenant) as s:
        row = s.scalar(select(Notice).where(Notice.public_id == n["id"]))
        assert row
        row.publish_at, row.expires_at = now - timedelta(days=10), now - timedelta(days=1)
    assert n["id"] not in board_ids(client, staff["member"])
    expired = client.get("/api/v1/notices?state=EXPIRED", headers=h).json()["items"]
    assert n["id"] in {x["id"] for x in expired}
    # "Publish now" and archive
    m = notice(client, h, title="Choir practice moved", publish_at=later.isoformat())
    client.post(f"/api/v1/notices/{m['id']}/submit", json={}, headers=h)
    approve_all(client, staff["president"], staff["priest"])
    r = client.post(f"/api/v1/notices/{m['id']}/publish", headers=h)
    assert r.json()["state"] == "LIVE" and m["id"] in board_ids(client, staff["member"])
    r = client.post(f"/api/v1/notices/{m['id']}/archive", headers=h)
    assert r.json()["status"] == "ARCHIVED" and m["id"] not in board_ids(client, staff["member"])


def test_audience_and_emergency(client: TestClient, tenant: TenantDescriptor, staff: dict) -> None:
    unit = make_org_unit(tenant, "SOCIETY", "Youth Society")
    with tenant_session_scope(tenant) as s:
        upid = s.get(OrgUnit, unit).public_id  # type: ignore[union-attr]
    youth = make_user(tenant, "SOCIETY_LEADER", unit=unit)
    outsider = make_user(tenant, "GENERAL_MEMBER")
    h = login(client, staff["secretary"])
    r = client.post(
        "/api/v1/notices",
        json={"title": "Youth retreat", "body": "Bring your Bibles.", "audience_all": False},
        headers=h,
    )
    assert r.status_code == 422  # targeted notices need organisations
    n = notice(
        client,
        h,
        title="Youth retreat",
        body="Bring your Bibles.",
        audience_all=False,
        audience_org_units=[upid],
        is_public=True,
    )
    assert n["is_public"] is False  # targeted notices never go to the public portal
    client.post(f"/api/v1/notices/{n['id']}/submit", json={}, headers=h)
    approve_all(client, staff["president"], staff["priest"])
    assert n["id"] in board_ids(client, youth)
    assert n["id"] not in board_ids(client, outsider)
    assert client.get(f"/api/v1/notices/{n['id']}", headers=login(client, outsider)).status_code == 404
    assert (
        notified(tenant, youth, "notice.published") == 1
        and notified(tenant, outsider, "notice.published") == 0
    )
    # Emergency: priest only (seeded fast workflow), always important.
    e = notice(client, h, title="Church closed today", category="EMERGENCY", body="Flooding near the church.")
    assert e["is_important"] is True
    inst = client.post(f"/api/v1/notices/{e['id']}/submit", json={}, headers=h).json()["approval_id"]
    d = client.get(f"/api/v1/workflow/instances/{inst}", headers=h).json()
    assert d["definition"]["code"] == "NOTICE_EMERGENCY" and d["pending_with"] == [staff["priest"].full_name]


def test_permissions_and_drafts(client: TestClient, tenant: TenantDescriptor, staff: dict) -> None:
    hm = login(client, staff["member"])
    assert (
        client.post("/api/v1/notices", json={"title": "Hello there", "body": "Spam"}, headers=hm).status_code
        == 403
    )
    assert client.get("/api/v1/notices", headers=hm).status_code == 403
    h = login(client, staff["secretary"])
    n = notice(client, h, title="Draft notice")
    assert client.get(f"/api/v1/notices/{n['id']}", headers=hm).status_code == 404
    r = client.put(
        f"/api/v1/notices/{n['id']}",
        json={"title": "Draft notice (edited)", "body": "Updated text"},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["title"] == "Draft notice (edited)"
    bad = {
        "title": "Bad dates",
        "body": "x y z",
        "publish_at": "2026-12-10T10:00",
        "expires_at": "2026-12-01T10:00",
    }
    assert client.post("/api/v1/notices", json=bad, headers=h).status_code == 422
    assert client.delete(f"/api/v1/notices/{n['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/notices/{n['id']}", headers=h).status_code == 404

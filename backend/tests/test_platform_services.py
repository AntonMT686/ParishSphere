"""Common platform services (T5): sequences, audit, storage, exports, notifications."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.audit import changes
from app.common.email import OUTBOX
from app.common.exports import Column, ExportFormat, export_table
from app.common.ratelimit import counter
from app.common.sequences import UnknownSequence, next_code, peek_code
from app.common.storage import (
    LocalStorage,
    build_key,
    get_storage,
    reset_storage,
    sign_download,
    validate_upload,
)
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.notifications import service as notify
from app.modules.notifications.models import Notification, OutboundMessage
from app.modules.rbac.service import assign_role, role_by_code, users_with_permission
from app.tenancy.resolver import resolve_tenant
from tests.conftest import auth, make_org_unit

HOST = {"Host": "svc.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = bytes.fromhex("89504E470D0A1A0A0000000D49484452") + b"\x00" * 32


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="SVC", name="Services Parish"))
        s.commit()
    return provision_parish("SVC")


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # type: ignore[no-untyped-def]
    counter().reset()
    OUTBOX.clear()
    monkeypatch.setattr(get_settings(), "storage_local_dir", tmp_path / "files")
    reset_storage()
    yield
    reset_storage()


def make_user(
    tenant: TenantDescriptor,
    *roles: str,
    email: str | None = None,
    lang: str = "en",
    org_unit_id: int | None = None,
) -> User:
    username = f"s{next(_n)}"
    with tenant_session_scope(tenant) as s:
        u = create_user(
            s,
            username=username,
            full_name=f"User {username}",
            password=PW,
            email=email,
            must_change_password=False,
        )
        u.preferred_language = lang
        for code in roles:
            role = role_by_code(s, code)
            assert role
            assign_role(s, u, role, org_unit_id=org_unit_id if role.scope_type != "PARISH" else None)
        s.flush()
        s.expunge(u)
    return u


def headers(client: TestClient, user: User) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": user.username, "password": PW}, headers=HOST)
    assert r.status_code == 200, r.text
    return {**HOST, **auth(r.json()["access_token"])}


# ----------------------------------------------------------------------------- sequences
def test_sequences(tenant: TenantDescriptor) -> None:
    with tenant_session_scope(tenant) as s:
        assert peek_code(s, "FAMILY") == "FAM000001"
        assert [next_code(s, "FAMILY") for _ in range(3)] == ["FAM000001", "FAM000002", "FAM000003"]
        assert next_code(s, "TRANSACTION", date(2026, 3, 1)) == "TXN-2026-000001"
        assert next_code(s, "TRANSACTION", date(2026, 12, 31)) == "TXN-2026-000002"
        assert next_code(s, "TRANSACTION", date(2027, 1, 1)) == "TXN-2027-000001"  # yearly reset
        assert peek_code(s, "TRANSACTION", date(2026, 5, 5)) == "TXN-2026-000003"
        assert next_code(s, "ACTIVITY", date(2026, 1, 1)) == "ACT-2026-0001"
        with pytest.raises(UnknownSequence):
            next_code(s, "NOPE")
    with tenant_session_scope(tenant) as s:  # persisted across transactions
        assert next_code(s, "FAMILY") == "FAM000004"


def test_audit_changes_helper(tenant: TenantDescriptor) -> None:
    u = make_user(tenant)
    with tenant_session_scope(tenant) as s:
        user = s.get(User, u.id)
        assert user
        user.full_name = "Changed Name"
        user.phone = "+91 98400 00000"
        old, new = changes(user)
        assert old == {"full_name": f"User {u.username}", "phone": None}
        assert new == {"full_name": "Changed Name", "phone": "+91 98400 00000"}


# ----------------------------------------------------------------------------- storage
def test_validate_upload() -> None:
    assert validate_upload("Baptism Register 1952.PDF", PDF).content_type == "application/pdf"
    assert validate_upload("photo.png", PNG).extension == "png"
    with pytest.raises(ValidationFailed) as e:
        validate_upload("script.exe", PDF)
    assert e.value.code == "INVALID_FILE_TYPE"
    with pytest.raises(ValidationFailed) as e:
        validate_upload("fake.pdf", PNG)  # spoofed extension
    assert e.value.code == "INVALID_FILE_TYPE"
    with pytest.raises(ValidationFailed) as e:
        validate_upload("empty.pdf", b"")
    assert e.value.code == "EMPTY_FILE"
    with pytest.raises(ValidationFailed):
        validate_upload("photo.png", PNG, allowed={"pdf"})
    ole = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64
    assert validate_upload("old-register.doc", ole).content_type == "application/msword"


def test_validate_upload_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    with pytest.raises(ValidationFailed) as e:
        validate_upload("a.pdf", PDF)
    assert e.value.code == "FILE_TOO_LARGE"


def test_xlsx_upload_detected() -> None:
    from openpyxl import Workbook

    buf = io.BytesIO()
    Workbook().save(buf)
    assert validate_upload("import.xlsx", buf.getvalue()).extension == "xlsx"


def test_local_storage_and_keys(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = LocalStorage(tmp_path)
    key = build_key("SVC", "documents", "pdf")
    assert key.startswith("svc/documents/") and key.endswith(".pdf")
    store.put(key, PDF, "application/pdf")
    assert store.exists(key) and store.get(key) == PDF
    store.delete(key)
    assert not store.exists(key)
    for bad in ("../etc/passwd", "/abs/path", "svc/../../x"):
        with pytest.raises(ValueError):
            store.put(bad, b"x", "text/plain")
    with pytest.raises(ValueError):
        build_key("SVC", "../evil", "pdf")


def test_signed_download_is_bound_to_parish(
    client: TestClient, tenant: TenantDescriptor, two_parishes: tuple[str, str]
) -> None:
    store = get_storage()
    key = build_key(tenant.code, "statements", "pdf")
    store.put(key, PDF, "application/pdf")
    url = store.download_url(
        key,
        filename="Statement March 2026.pdf",
        content_type="application/pdf",
        tenant_public_id=tenant.public_id,
    )
    r = client.get(url, headers=HOST)
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert (
        "attachment" in r.headers["content-disposition"] and "Statement" in r.headers["content-disposition"]
    )
    # Same token on another parish's host → refused.
    assert client.get(url, headers={"Host": "stmarys.parishsphere.test"}).status_code == 404
    # Token minted for another parish but naming this parish's key → refused.
    other = resolve_tenant(code="STMARYS")
    assert other
    forged = sign_download(key, "x.pdf", "application/pdf", other.public_id)
    assert client.get(f"/api/v1/files/download?token={forged}", headers=HOST).status_code == 404
    assert client.get(f"/api/v1/files/download?token={'x' * 40}", headers=HOST).status_code == 404
    expired = sign_download(key, "x.pdf", "application/pdf", tenant.public_id, ttl=-1)
    r = client.get(f"/api/v1/files/download?token={expired}", headers=HOST)
    assert r.status_code == 404 and r.json()["error"]["code"] == "DOWNLOAD_LINK_INVALID"


def test_s3_storage_with_moto(monkeypatch: pytest.MonkeyPatch) -> None:
    from moto import mock_aws
    from pydantic import SecretStr

    s = get_settings()
    for k, v in {
        "storage_backend": "s3",
        "s3_bucket": "ps-test",
        "s3_region": "us-east-1",
        "s3_auto_create_bucket": True,
        "s3_endpoint_url": None,
        "s3_access_key": SecretStr("test"),
        "s3_secret_key": SecretStr("test"),
    }.items():
        monkeypatch.setattr(s, k, v)
    with mock_aws():
        reset_storage()
        store = get_storage()
        key = build_key("SVC", "documents", "pdf")
        store.put(key, PDF, "application/pdf")
        assert store.exists(key) and store.get(key) == PDF
        url = store.download_url(key, filename="a.pdf", content_type="application/pdf", tenant_public_id="x")
        assert "X-Amz-Signature" in url and "ps-test" in url
        store.delete(key)
        assert not store.exists(key)


# ----------------------------------------------------------------------------- exports
ROWS = [
    {
        "code": "FAM000001",
        "name": "ஆரோக்கியசாமி குடும்பம்",
        "members": 5,
        "joined": date(2020, 1, 5),
        "note": "=1+1",
    },
    {"code": "FAM000002", "name": "D'Souza", "members": 3, "joined": date(2021, 6, 1), "note": "@cmd"},
]
COLS = [
    Column("code", "Family ID"),
    Column("name", "Family"),
    Column("members", "Members", numeric=True),
    Column("joined", "Registered"),
    Column("note", "Note"),
]


def test_export_csv() -> None:
    r = export_table(ROWS, COLS, "csv", title="Family register", filename="families")
    body = r.body.decode("utf-8")
    assert body.startswith("﻿Family ID,Family")
    assert "ஆரோக்கியசாமி" in body and "'=1+1" in body and "'@cmd" in body
    assert "families-" in r.headers["content-disposition"] and r.headers["content-disposition"].count(".csv")


def test_export_xlsx() -> None:
    from openpyxl import load_workbook

    r = export_table(ROWS, COLS, ExportFormat.XLSX, title="Family register", filename="families")
    ws = load_workbook(io.BytesIO(r.body)).active
    assert [c.value for c in ws[1]] == ["Family ID", "Family", "Members", "Registered", "Note"]
    assert ws["B2"].value == "ஆரோக்கியசாமி குடும்பம்" and ws["C2"].value == 5
    assert ws["E2"].data_type == "s" and ws["E2"].value == "=1+1"  # text, never a formula
    assert ws.freeze_panes == "A2"


def test_export_pdf() -> None:
    r = export_table(
        ROWS, COLS, "pdf", title="Family register", filename="families", parish_name="St. Mary's"
    )
    assert r.body[:5] == b"%PDF-" and len(r.body) > 1000
    assert r.media_type == "application/pdf"


def test_export_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "max_export_rows", 1)
    with pytest.raises(ValidationFailed) as e:
        export_table(ROWS, COLS, "csv", title="x", filename="x")
    assert e.value.code == "EXPORT_TOO_LARGE"


# ----------------------------------------------------------------------------- audit API
def test_audit_log_api(client: TestClient, tenant: TenantDescriptor) -> None:
    admin = make_user(tenant, "PARISH_ADMIN")
    h = headers(client, admin)
    client.post("/api/v1/auth/login", json={"username": admin.username, "password": "wrong"}, headers=HOST)
    r = client.get("/api/v1/audit-logs?action=login_failed&module=auth", headers=h)
    assert r.status_code == 200 and r.json()["total"] >= 1
    item = r.json()["items"][0]
    assert item["action"] == "LOGIN_FAILED" and item["username"] == admin.username
    r = client.get(f"/api/v1/audit-logs?user={item['user_id']}&date_from={date.today()}", headers=h)
    assert r.json()["total"] >= 2  # LOGIN + LOGIN_FAILED

    for fmt, ctype in (("xlsx", "spreadsheetml"), ("csv", "text/csv"), ("pdf", "application/pdf")):
        r = client.get(f"/api/v1/audit-logs/export?format={fmt}&module=auth", headers=h)
        assert r.status_code == 200 and ctype in r.headers["content-type"], fmt
    r = client.get("/api/v1/audit-logs?action=EXPORT", headers=h)
    assert r.json()["total"] == 3

    clerk = make_user(tenant, "PARISH_TREASURER")
    assert client.get("/api/v1/audit-logs", headers=headers(client, clerk)).status_code == 403


# ----------------------------------------------------------------------------- notifications
def test_emit_creates_in_app_and_delivers_email_after_commit(tenant: TenantDescriptor) -> None:
    u = make_user(tenant, email="sec@svc.org")
    with tenant_session_scope(tenant) as s:
        created = notify.emit(
            s,
            tenant,
            "approval.pending",
            [u.id],
            {
                "entity_label": "Activity",
                "title": "Youth Camp",
                "stage": "Parish Priest",
                "submitted_by": "Youth Secretary",
            },
            link="/activities/X",
        )
        assert len(created) == 1 and created[0].title == "Approval needed: Youth Camp"
        assert OUTBOX == []  # nothing sent before commit
    assert len(OUTBOX) == 1
    msg = OUTBOX[0]
    assert msg["To"] == "sec@svc.org" and msg["Subject"] == "Services Parish: Approval needed: Youth Camp"
    assert "http://svc.parishsphere.localhost/activities/X" in msg.get_content()
    with tenant_session_scope(tenant) as s:
        out = s.scalars(select(OutboundMessage).where(OutboundMessage.recipient == "sec@svc.org")).one()
        assert out.status == "SENT" and out.attempts == 1 and out.sent_at


def test_rollback_sends_nothing(tenant: TenantDescriptor) -> None:
    u = make_user(tenant, email="rb@svc.org")
    with pytest.raises(RuntimeError), tenant_session_scope(tenant) as s:
        notify.emit(s, tenant, "workflow.approved", [u.id], {"entity_label": "Notice", "title": "X"})
        raise RuntimeError("business failure")
    assert OUTBOX == []
    with tenant_session_scope(tenant) as s:
        assert s.scalars(select(Notification).where(Notification.user_id == u.id)).first() is None


def test_tamil_templates_and_default_channels(tenant: TenantDescriptor) -> None:
    u = make_user(tenant, email="ta@svc.org", lang="ta")
    with tenant_session_scope(tenant) as s:
        n = notify.emit(s, tenant, "notice.published", [u], {"title": "ஞாயிறு திருப்பலி"})[0]
        assert n.title == "புதிய அறிவிப்பு: ஞாயிறு திருப்பலி"
    assert OUTBOX == []  # notice.published is in-app only by default


def test_delivery_failure_and_retry(tenant: TenantDescriptor, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.notifications import service as svc

    u = make_user(tenant, email="fail@svc.org")
    calls = {"n": 0}

    def flaky(*_a, **_k):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        raise OSError("smtp down")

    monkeypatch.setattr(svc, "send_email", flaky)
    with tenant_session_scope(tenant) as s:
        notify.emit(s, tenant, "workflow.approved", [u.id], {"entity_label": "Activity", "title": "A"})
    with tenant_session_scope(tenant) as s:
        msg = s.scalars(select(OutboundMessage).where(OutboundMessage.recipient == "fail@svc.org")).one()
        assert msg.status == "FAILED" and msg.attempts == 1 and "smtp down" in (msg.last_error or "")
        mid = msg.id
    monkeypatch.undo()
    assert notify.deliver(tenant.code, mid) == "SENT"
    assert notify.deliver(tenant.code, mid) == "SKIPPED"  # idempotent
    monkeypatch.setattr(svc, "send_email", flaky)
    with tenant_session_scope(tenant) as s:
        notify.emit(s, tenant, "workflow.approved", [u.id], {"entity_label": "Activity", "title": "B"})
    with tenant_session_scope(tenant) as s:
        new_id = max(s.scalars(select(OutboundMessage.id)))
    with pytest.raises(OSError):  # the Celery task path re-raises so the task can be retried
        notify.deliver(tenant.code, new_id, raise_errors=True)
    assert calls["n"] == 3


def test_celery_task_dispatch(tenant: TenantDescriptor, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.notifications import tasks

    sent: list[tuple[str, int]] = []
    monkeypatch.setattr(get_settings(), "notifications_async", True)
    monkeypatch.setattr(tasks.send_outbound, "delay", lambda code, mid: sent.append((code, mid)))
    u = make_user(tenant, email="celery@svc.org")
    with tenant_session_scope(tenant) as s:
        notify.emit(s, tenant, "workflow.approved", [u.id], {"entity_label": "Activity", "title": "C"})
    assert len(sent) == 1 and sent[0][0] == "SVC" and OUTBOX == []
    assert tasks.send_outbound.run("SVC", sent[0][1]) == "SENT"


def test_template_rendering_is_sandboxed() -> None:
    with pytest.raises(Exception):  # noqa: B017
        notify.render("{{ ''.__class__.__mro__[1].__subclasses__() }}", {})
    with pytest.raises(ValidationFailed):
        notify.validate_template("notice.published", "{{ title", "x")


def test_notifications_api(client: TestClient, tenant: TenantDescriptor) -> None:
    admin = make_user(tenant, "PARISH_ADMIN")
    member = make_user(tenant, "GENERAL_MEMBER", email="member@svc.org")
    ha, hm = headers(client, admin), headers(client, member)

    # Admin overrides the English in-app template, then broadcasts to general members.
    r = client.put(
        "/api/v1/notifications/templates/general.message/IN_APP/en",
        json={"subject": "📢 {{ title }}", "body": "{{ message }} — Parish Office"},
        headers=ha,
    )
    assert r.status_code == 200 and r.json()["is_override"]
    bad = client.put(
        "/api/v1/notifications/templates/general.message/IN_APP/en",
        json={"subject": "{% if %}", "body": "x"},
        headers=ha,
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_TEMPLATE"
    assert (
        client.put(
            "/api/v1/notifications/templates/nope/IN_APP/en", json={"subject": "a", "body": "b"}, headers=ha
        ).status_code
        == 404
    )

    r = client.post(
        "/api/v1/notifications/broadcast",
        json={"title": "Choir practice", "message": "Friday 6pm", "role_codes": ["GENERAL_MEMBER"]},
        headers=ha,
    )
    assert r.status_code == 202 and r.json()["recipients"] >= 1
    assert (
        client.post(
            "/api/v1/notifications/broadcast", json={"title": "x", "message": "y"}, headers=hm
        ).status_code
        == 403
    )

    assert client.get("/api/v1/notifications/unread-count", headers=hm).json()["unread"] == 1
    items = client.get("/api/v1/notifications", headers=hm).json()["items"]
    assert items[0]["title"] == "📢 Choir practice" and items[0]["body"] == "Friday 6pm — Parish Office"
    assert items[0]["is_important"] is True
    r = client.post(f"/api/v1/notifications/{items[0]['id']}/read", headers=hm)
    assert r.json()["is_read"] is True
    assert client.get("/api/v1/notifications?unread_only=true", headers=hm).json()["total"] == 0
    # Another user's notification id is not reachable.
    assert client.post(f"/api/v1/notifications/{items[0]['id']}/read", headers=ha).status_code == 404
    assert client.post("/api/v1/notifications/read-all", headers=hm).json() == {"unread": 0}

    assert (
        client.delete("/api/v1/notifications/templates/general.message/IN_APP/en", headers=ha).status_code
        == 204
    )
    tpl = next(
        t
        for t in client.get("/api/v1/notifications/templates", headers=ha).json()
        if t["event_code"] == "general.message" and t["channel"] == "IN_APP" and t["language"] == "en"
    )
    assert tpl["is_override"] is False and tpl["subject"] == "{{ title }}"


def test_preferences(client: TestClient, tenant: TenantDescriptor) -> None:
    u = make_user(tenant, email="prefs@svc.org")
    h = headers(client, u)
    prefs = {
        (p["event_code"], p["channel"]): p
        for p in client.get("/api/v1/notifications/preferences", headers=h).json()
    }
    assert prefs[("approval.pending", "EMAIL")]["enabled"] is True
    assert prefs[("notice.published", "EMAIL")]["enabled"] is False
    r = client.put(
        "/api/v1/notifications/preferences",
        json=[{"event_code": "approval.pending", "channel": "EMAIL", "enabled": False}],
        headers=h,
    )
    assert r.status_code == 200
    bad = client.put(
        "/api/v1/notifications/preferences",
        json=[{"event_code": "x.y", "channel": "EMAIL", "enabled": True}],
        headers=h,
    )
    assert bad.status_code == 422
    with tenant_session_scope(tenant) as s:
        notify.emit(
            s,
            tenant,
            "approval.pending",
            [u.id],
            {"entity_label": "Activity", "title": "T", "stage": "S", "submitted_by": "B"},
        )
    assert OUTBOX == []  # email disabled by the user; in-app still delivered
    assert client.get("/api/v1/notifications/unread-count", headers=h).json()["unread"] == 1


def test_users_with_permission_scope(tenant: TenantDescriptor) -> None:
    priest = make_user(tenant, "PARISH_PRIEST")
    unit_a, unit_b = make_org_unit(tenant), make_org_unit(tenant)
    sec_a = make_user(tenant, "COMMITTEE_SECRETARY", org_unit_id=unit_a)
    sec_b = make_user(tenant, "COMMITTEE_SECRETARY", org_unit_id=unit_b)
    with tenant_session_scope(tenant) as s:
        ids = {u.id for u in users_with_permission(s, "activity.create", unit_a)}
        assert priest.id in ids and sec_a.id in ids and sec_b.id not in ids
        assert sec_a.id not in {u.id for u in users_with_permission(s, "activity.create")}
        assert {u.id for u in users_with_permission(s, "activity.approve", role_code="PARISH_PRIEST")} >= {
            priest.id
        }


def test_audit_log_is_append_only(tenant) -> None:  # type: ignore[no-untyped-def]
    """No code path may rewrite history: ORM updates, deletes and bulk statements are all refused."""
    from sqlalchemy import delete, select, update

    from app.common.audit import AuditTamperError, record_audit
    from app.db.tenant import tenant_session_scope
    from app.modules.core.models import AuditLog

    with tenant_session_scope(tenant) as s:
        row = record_audit(s, action="TEST", module="tests", remarks="original")
        s.flush()
        rid = row.id
    for attempt in ("modify", "delete", "bulk_update", "bulk_delete"):
        with pytest.raises(AuditTamperError), tenant_session_scope(tenant) as s:
            log = s.get(AuditLog, rid)
            assert log is not None
            if attempt == "modify":
                log.remarks = "rewritten"
                s.flush()
            elif attempt == "delete":
                s.delete(log)
                s.flush()
            elif attempt == "bulk_update":
                s.execute(update(AuditLog).where(AuditLog.id == rid).values(remarks="x"))
            else:
                s.execute(delete(AuditLog).where(AuditLog.id == rid))
    with tenant_session_scope(tenant) as s:
        assert s.scalar(select(AuditLog.remarks).where(AuditLog.id == rid)) == "original"

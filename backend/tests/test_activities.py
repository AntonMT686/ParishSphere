"""Activities, meetings, minutes, action items and calendar (T11)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.ratelimit import counter
from app.common.storage import reset_storage
from app.core.config import get_settings
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.activities import service as svc
from app.modules.activities.models import ActionItem, Meeting
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.notifications.models import Notification
from app.modules.org_units import service as org_svc
from app.modules.org_units.models import OrgUnit
from app.modules.people.models import Family, Member, OrgUnitMembership
from app.modules.rbac.service import assign_role, role_by_code
from tests.conftest import auth, make_org_unit

HOST = {"Host": "act.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
TODAY = date.today()


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="ACT", name="St. Sebastian's Church"))
        s.commit()
    return provision_parish("ACT")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # type: ignore[no-untyped-def]
    counter().reset()
    monkeypatch.setattr(get_settings(), "storage_local_dir", tmp_path / "files")
    reset_storage()
    yield
    reset_storage()


def make_user(tenant: TenantDescriptor, *roles: str, unit: int | None = None) -> User:
    username = f"a{next(_n)}"
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


def unit_public(tenant: TenantDescriptor, unit_id: int) -> str:
    with tenant_session_scope(tenant) as s:
        u = s.get(OrgUnit, unit_id)
        assert u
        return u.public_id


def appoint_president(tenant: TenantDescriptor, unit_id: int, user: User, type_code: str = "SOCIETY") -> None:
    with tenant_session_scope(tenant) as s:
        pos = next(p for p in org_svc.get_type(s, type_code).positions if p.code == "PRESIDENT")
        org_svc.appoint(s, s.get(OrgUnit, unit_id), pos, user=s.get(User, user.id), holder_name=None)  # type: ignore[arg-type]


def notified(tenant: TenantDescriptor, user: User, event: str) -> int:
    with tenant_session_scope(tenant) as s:
        return len(
            s.scalars(
                select(Notification).where(Notification.user_id == user.id, Notification.event_code == event)
            ).all()
        )


def decide(client: TestClient, user: User, action: str = "APPROVE", comment: str | None = None) -> dict:
    h = login(client, user)
    tasks = client.get("/api/v1/workflow/tasks", headers=h).json()["items"]
    assert len(tasks) == 1, tasks
    r = client.post(
        f"/api/v1/workflow/tasks/{tasks[0]['id']}/act", json={"action": action, "comment": comment}, headers=h
    )
    assert r.status_code == 200, r.text
    return r.json()


def activity_body(unit: str | None, **kw) -> dict:  # type: ignore[no-untyped-def]
    return {
        "org_unit_id": unit,
        "title": "Youth retreat",
        "category": "SPIRITUAL",
        "activity_date": str(TODAY),
        "location": "Kodaikanal",
        "planned_details": "Two days of talks",
        "planned_amount": "15000.00",
        "participants": [{"name": "Guest speaker", "role": "Speaker"}],
        **kw,
    }


# ============================================================================ activities
def test_activity_three_stage_approval_rework_and_completion(
    client: TestClient, tenant: TenantDescriptor
) -> None:
    society = make_org_unit(tenant, "SOCIETY", "Youth Society")
    sid = unit_public(tenant, society)
    secretary = make_user(tenant, "COMMITTEE_SECRETARY", unit=society)
    president = make_user(tenant)
    appoint_president(tenant, society, president)
    parish_secretary = make_user(tenant, "PARISH_SECRETARY")
    priest = make_user(tenant, "PARISH_PRIEST")
    h = login(client, secretary)

    r = client.post("/api/v1/activities", json=activity_body(sid), headers=h)
    assert r.status_code == 201, r.text
    act = r.json()
    assert act["code"].startswith(f"ACT-{TODAY.year}-") and act["status"] == "DRAFT"
    assert act["can"]["edit"] and act["can"]["submit"] and act["participants"][0]["name"] == "Guest speaker"
    aid = act["id"]

    r = client.post(f"/api/v1/activities/{aid}/submit", json={}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "IN_REVIEW" and r.json()["approval_id"]
    # Locked while under review.
    r = client.put(f"/api/v1/activities/{aid}", json=activity_body(sid, title="Changed"), headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_EDITABLE"

    decide(client, president)  # stage 1: President of the organisation (office bearer)
    decide(client, parish_secretary, "RETURN", "Add the budget split")
    assert client.get(f"/api/v1/activities/{aid}", headers=h).json()["status"] == "REWORK"
    r = client.put(
        f"/api/v1/activities/{aid}", json=activity_body(sid, planned_details="Talks; ₹10k travel"), headers=h
    )
    assert r.status_code == 200
    r = client.post(f"/api/v1/activities/{aid}/submit", json={"comment": "Budget added"}, headers=h)
    assert r.json()["status"] == "IN_REVIEW"
    decide(client, president)
    decide(client, parish_secretary)
    decide(client, priest)
    act = client.get(f"/api/v1/activities/{aid}", headers=h).json()
    assert act["status"] == "APPROVED" and act["approved_at"] and act["can"]["complete"]

    r = client.post(
        f"/api/v1/activities/{aid}/complete",
        json={"actual_details": "42 youth attended", "actual_amount": "13200", "participant_count": 42},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED" and r.json()["participant_count"] == 42
    assert notified(tenant, secretary, "workflow.approved") == 1


def test_activity_scope_and_drafts(client: TestClient, tenant: TenantDescriptor) -> None:
    mine, other = (
        make_org_unit(tenant, "SOCIETY", "Choir"),
        make_org_unit(tenant, "SOCIETY", "Legion of Mary"),
    )
    sec = make_user(tenant, "COMMITTEE_SECRETARY", unit=mine)
    h = login(client, sec)
    assert (
        client.post(
            "/api/v1/activities", json=activity_body(unit_public(tenant, other)), headers=h
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/activities", json=activity_body(None), headers=h).status_code == 403
    )  # parish-level
    other_sec = make_user(tenant, "COMMITTEE_SECRETARY", unit=other)
    theirs = client.post(
        "/api/v1/activities",
        json=activity_body(unit_public(tenant, other), title="Rosary"),
        headers=login(client, other_sec),
    ).json()
    listed = client.get("/api/v1/activities", headers=h).json()["items"]
    assert theirs["id"] not in {a["id"] for a in listed}
    assert client.get(f"/api/v1/activities/{theirs['id']}", headers=h).status_code == 404
    # Draft deletion; parish secretary sees and can record parish-level activities.
    a = client.post(
        "/api/v1/activities", json=activity_body(unit_public(tenant, mine), title="Carols"), headers=h
    ).json()
    assert client.delete(f"/api/v1/activities/{a['id']}", headers=h).status_code == 204
    hp = login(client, make_user(tenant, "PARISH_SECRETARY"))
    r = client.post("/api/v1/activities", json=activity_body(None, title="Parish feast"), headers=hp)
    assert r.status_code == 201 and r.json()["org_unit"] is None
    assert theirs["id"] in {
        x["id"] for x in client.get("/api/v1/activities?size=100", headers=hp).json()["items"]
    }
    bad = activity_body(None, end_date=str(TODAY - timedelta(days=1)))
    assert client.post("/api/v1/activities", json=bad, headers=hp).status_code == 422


def test_activity_attachments_and_export(client: TestClient, tenant: TenantDescriptor) -> None:
    unit = make_org_unit(tenant, "SOCIETY", "Women's Society")
    h = login(client, make_user(tenant, "SOCIETY_LEADER", unit=unit))
    a = client.post("/api/v1/activities", json=activity_body(unit_public(tenant, unit)), headers=h).json()
    r = client.post(
        f"/api/v1/activities/{a['id']}/attachments",
        files={"file": ("report.pdf", PDF, "application/pdf")},
        headers=h,
    )
    assert r.status_code == 201, r.text
    fid, url = r.json()["id"], r.json()["url"]
    assert client.get(url, headers=HOST).content == PDF
    bad = client.post(
        f"/api/v1/activities/{a['id']}/attachments",
        files={"file": ("x.pdf", b"MZ\x90\x00", "a/b")},
        headers=h,
    )
    assert bad.status_code == 422
    assert len(client.get(f"/api/v1/activities/{a['id']}/attachments", headers=h).json()) == 1
    assert client.delete(f"/api/v1/activities/{a['id']}/attachments/{fid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/activities/{a['id']}/attachments", headers=h).json() == []
    hp = login(client, make_user(tenant, "PARISH_PRIEST"))
    r = client.get("/api/v1/activities/export?format=xlsx", headers=hp)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert client.get("/api/v1/activities/export", headers=h).status_code == 403  # no activity.export


# ============================================================================ meetings
def test_meeting_schedule_attendance_minutes_approval_pdf(
    client: TestClient, tenant: TenantDescriptor
) -> None:
    unit = make_org_unit(tenant, "COMMITTEE", "Liturgy Committee")
    upid = unit_public(tenant, unit)
    president = make_user(tenant)
    appoint_president(tenant, unit, president, "COMMITTEE")
    priest = make_user(tenant, "PARISH_PRIEST")
    sec = make_user(tenant, "COMMITTEE_SECRETARY", unit=unit)
    h = login(client, sec)
    # Members of the committee pre-fill the attendance list.
    with tenant_session_scope(tenant) as s:
        fam = Family(
            code=f"FAM9{next(_n):05d}", family_name="Rayappan", search_name="rayappan", status="ACTIVE"
        )
        s.add(fam)
        s.flush()
        for first in ("Arul", "Jessy"):
            m = Member(
                code=f"MEM9{next(_n):05d}",
                family_id=fam.id,
                first_name=first,
                search_name=first.lower(),
                gender="M",
                relationship_to_head="HEAD" if first == "Arul" else "SPOUSE",
                status="ACTIVE",
            )
            s.add(m)
            s.flush()
            s.add(OrgUnitMembership(org_unit_id=unit, member_id=m.id, joined_on=TODAY - timedelta(days=30)))
    when = datetime.now().replace(microsecond=0, second=0) + timedelta(days=3)
    body = {
        "org_unit_id": upid,
        "title": "Monthly meeting",
        "scheduled_at": when.isoformat(),
        "location": "Parish hall",
        "agenda": [{"title": "Christmas liturgy"}, {"title": "Choir roster", "presenter": "Jessy"}],
    }
    r = client.post("/api/v1/meetings", json=body, headers=h)
    assert r.status_code == 201, r.text
    mtg = r.json()
    assert mtg["code"].startswith("MTG-") and [a["seq"] for a in mtg["agenda"]] == [1, 2]
    assert notified(tenant, president, "meeting.scheduled") == 1
    att = client.get(f"/api/v1/meetings/{mtg['id']}/attendance", headers=h).json()
    assert att["recorded"] is False and att["rows"][0]["name"].startswith("Arul")
    # Minutes only after the meeting took place.
    r = client.put(f"/api/v1/meetings/{mtg['id']}/minutes", json={"summary": "x"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "MEETING_NOT_HELD"
    with tenant_session_scope(tenant) as s:
        m = s.scalar(select(Meeting).where(Meeting.public_id == mtg["id"]))
        assert m
        m.scheduled_at = m.scheduled_at - timedelta(days=4)
    rows = [{**x, "status": "PRESENT"} for x in att["rows"]]
    rows[1]["status"] = "EXCUSED"
    att = client.put(f"/api/v1/meetings/{mtg['id']}/attendance", json={"rows": rows}, headers=h).json()
    assert att["recorded"] and att["present"] == 1 and att["total"] == 2
    minutes = {
        "summary": "Opened with prayer.",
        "points": [{"topic": "Christmas liturgy", "discussion": "Midnight mass"}],
        "resolutions": [{"text": "Hire a sound system", "decision": "PASSED"}],
    }
    r = client.put(f"/api/v1/meetings/{mtg['id']}/minutes", json=minutes, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "HELD" and r.json()["minutes"]["status"] == "DRAFT"
    r = client.post(f"/api/v1/meetings/{mtg['id']}/minutes/submit", json={}, headers=h)
    assert r.json()["minutes"]["status"] == "IN_REVIEW" and not r.json()["minutes"]["can_edit"]
    assert client.put(f"/api/v1/meetings/{mtg['id']}/minutes", json=minutes, headers=h).status_code == 409
    assert (
        client.put(f"/api/v1/meetings/{mtg['id']}/attendance", json={"rows": rows}, headers=h).status_code
        == 409
    )
    decide(client, president)
    decide(client, priest)
    got = client.get(f"/api/v1/meetings/{mtg['id']}", headers=h).json()
    assert got["minutes"]["status"] == "APPROVED" and got["minutes"]["approved_at"]
    pdf = client.get(f"/api/v1/meetings/{mtg['id']}/minutes.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_meeting_cancel_and_scope(client: TestClient, tenant: TenantDescriptor) -> None:
    unit = make_org_unit(tenant, "ANBIYAM", "St. Joseph Anbiyam")
    president = make_user(tenant)
    appoint_president(tenant, unit, president, "ANBIYAM")
    leader = make_user(tenant, "ANBIYAM_LEADER", unit=unit)
    with tenant_session_scope(tenant) as s:
        s.add(
            Family(
                code=f"FAM8{next(_n):05d}",
                family_name="Antony",
                search_name="antony",
                status="ACTIVE",
                anbiyam_id=unit,
            )
        )
    h = login(client, leader)
    when = (datetime.now() + timedelta(days=2)).replace(microsecond=0, second=0)
    mtg = client.post(
        "/api/v1/meetings",
        json={
            "org_unit_id": unit_public(tenant, unit),
            "title": "Anbiyam prayer",
            "scheduled_at": when.isoformat(),
        },
        headers=h,
    ).json()
    att = client.get(f"/api/v1/meetings/{mtg['id']}/attendance", headers=h).json()
    assert (
        att["rows"][0]["name"].startswith("Antony (") and att["rows"][0]["family_id"]
    )  # families for Anbiyam
    outsider = login(client, make_user(tenant, "COMMITTEE_SECRETARY", unit=make_org_unit(tenant)))
    assert client.get(f"/api/v1/meetings/{mtg['id']}", headers=outsider).status_code == 404
    r = client.post(f"/api/v1/meetings/{mtg['id']}/cancel", json={"reason": "Rain"}, headers=h)
    assert r.json()["status"] == "CANCELLED" and notified(tenant, president, "meeting.cancelled") == 1
    assert client.get("/api/v1/meetings?when=upcoming", headers=h).json()["total"] == 0


# ============================================================================ action items
def test_action_items_assignment_progress_and_visibility(
    client: TestClient, tenant: TenantDescriptor
) -> None:
    unit = make_org_unit(tenant, "COMMITTEE", "Building Committee")
    sec = make_user(tenant, "COMMITTEE_SECRETARY", unit=unit)
    owner = make_user(tenant, "GENERAL_MEMBER")  # no action-item permissions at all
    h = login(client, sec)
    when = (datetime.now() - timedelta(days=1)).replace(microsecond=0, second=0)
    mtg = client.post(
        "/api/v1/meetings",
        json={
            "org_unit_id": unit_public(tenant, unit),
            "title": "Roof",
            "scheduled_at": when.isoformat(),
            "notify": False,
        },
        headers=h,
    ).json()
    r = client.post(
        "/api/v1/action-items",
        json={
            "title": "Get three quotations",
            "meeting_id": mtg["id"],
            "owner_user_id": owner.public_id,
            "due_date": str(TODAY + timedelta(days=7)),
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert (
        item["source"] == {"type": "MEETING", "id": mtg["id"], "title": "Roof"}
        and item["owner"]["id"] == owner.public_id
    )
    assert notified(tenant, owner, "action_item.assigned") == 1
    ho = login(client, owner)
    mine = client.get("/api/v1/action-items?mine=true", headers=ho).json()
    assert [i["id"] for i in mine["items"]] == [item["id"]] and mine["items"][0]["can_update"]
    assert client.get("/api/v1/action-items/summary", headers=ho).json() == {"open": 1, "overdue": 0}
    r = client.post(
        f"/api/v1/action-items/{item['id']}/progress",
        json={"text": "Two received", "progress_pct": 60},
        headers=ho,
    )
    assert r.json()["status"] == "IN_PROGRESS" and r.json()["progress_pct"] == 60
    r = client.post(f"/api/v1/action-items/{item['id']}/progress", json={"status": "DONE"}, headers=ho)
    assert r.json()["status"] == "DONE" and r.json()["progress_pct"] == 100 and r.json()["completed_on"]
    # Reopening needs a coordinator; the owner cannot edit the item itself.
    assert (
        client.post(
            f"/api/v1/action-items/{item['id']}/progress", json={"status": "OPEN"}, headers=ho
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/api/v1/action-items/{item['id']}", json={"title": "Other"}, headers=ho).status_code
        == 403
    )
    r = client.post(
        f"/api/v1/action-items/{item['id']}/progress",
        json={"status": "OPEN", "text": "Need a 3rd"},
        headers=h,
    )
    assert r.json()["status"] == "OPEN" and r.json()["completed_on"] is None and len(r.json()["updates"]) == 3
    # Someone neither responsible nor in the organisation cannot see it.
    stranger = login(client, make_user(tenant, "GENERAL_MEMBER"))
    assert client.get(f"/api/v1/action-items/{item['id']}", headers=stranger).status_code == 404
    # A manual item needs an owner.
    r = client.post(
        "/api/v1/action-items", json={"title": "Paint", "org_unit_id": unit_public(tenant, unit)}, headers=h
    )
    assert r.status_code == 422


def test_reminders(tenant: TenantDescriptor) -> None:
    unit = make_org_unit(tenant, "COMMITTEE", "Festival Committee")
    pres, owner = make_user(tenant), make_user(tenant)
    appoint_president(tenant, unit, pres, "COMMITTEE")
    with tenant_session_scope(tenant) as s:
        now = svc.parish_now(s)
        s.add(
            Meeting(
                code=f"MTG-T{next(_n)}",
                org_unit_id=unit,
                title="Festival planning",
                status="SCHEDULED",
                scheduled_at=now + timedelta(hours=20),
            )
        )
        for i, due in enumerate(
            (now.date() + timedelta(days=1), now.date() - timedelta(days=10), now.date() + timedelta(days=5))
        ):
            s.add(
                ActionItem(
                    code=f"AI-T{next(_n)}",
                    title=f"Task {i}",
                    owner_user_id=owner.id,
                    due_date=due,
                    status="OPEN",
                    progress_pct=0,
                    org_unit_id=unit,
                )
            )
    with tenant_session_scope(tenant) as s:
        r = svc.run_reminders(s, tenant)
    assert r["meetings"] >= 1 and r["action_items"] == 2
    with tenant_session_scope(tenant) as s:
        r = svc.run_reminders(s, tenant)  # same day: nothing new
    assert r == {"meetings": 0, "action_items": 0}
    assert notified(tenant, pres, "meeting.reminder") == 1 and notified(tenant, owner, "action_item.due") == 2
    with tenant_session_scope(tenant) as s:  # a week later the overdue item is reminded again
        r = svc.run_reminders(s, tenant, svc.parish_now(s) + timedelta(days=7))
    assert r["action_items"] >= 1


# ============================================================================ calendar
def test_calendar(client: TestClient, tenant: TenantDescriptor) -> None:
    unit = make_org_unit(tenant, "SABAI", "St. Vincent de Paul")
    h = login(client, make_user(tenant, "SABAI_LEADER", unit=unit))
    upid = unit_public(tenant, unit)
    client.post("/api/v1/activities", json=activity_body(upid, title="Food drive"), headers=h)
    when = datetime.combine(TODAY, datetime.min.time()).replace(hour=18)
    client.post(
        "/api/v1/meetings",
        json={
            "org_unit_id": upid,
            "title": "Sabai meeting",
            "scheduled_at": when.isoformat(),
            "notify": False,
        },
        headers=h,
    )
    r = client.get(
        f"/api/v1/calendar?start={TODAY - timedelta(days=3)}&end={TODAY + timedelta(days=3)}&org_unit={upid}",
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert [(e["kind"], e["title"]) for e in r.json()] == [
        ("ACTIVITY", "Food drive"),
        ("MEETING", "Sabai meeting"),
    ]
    assert (
        client.get(f"/api/v1/calendar?start={TODAY}&end={TODAY + timedelta(days=200)}", headers=h).status_code
        == 422
    )
    member = login(client, make_user(tenant, "GENERAL_MEMBER"))
    assert client.get(f"/api/v1/calendar?start={TODAY}&end={TODAY}", headers=member).json() == []


def test_my_units_for_pickers(client: TestClient, tenant: TenantDescriptor) -> None:
    mine = make_org_unit(tenant, "SOCIETY", "Altar Servers")
    child = make_org_unit(tenant, "SOCIETY", "Junior Altar Servers", parent_id=mine)
    h = login(client, make_user(tenant, "SOCIETY_LEADER", unit=mine))
    r = client.get("/api/v1/org-units/mine?permission=activity.create", headers=h).json()
    assert r["parish"] is False
    assert {u["name"] for u in r["units"]} == {"Altar Servers", "Junior Altar Servers"}  # roles flow down
    assert unit_public(tenant, child) in {u["id"] for u in r["units"]}
    hp = login(client, make_user(tenant, "PARISH_SECRETARY"))
    r = client.get("/api/v1/org-units/mine?permission=activity.create", headers=hp).json()
    assert r["parish"] is True and len(r["units"]) >= 2
    assert client.get("/api/v1/org-units/mine?permission=nope.x", headers=hp).status_code == 422


def test_user_lookup_for_assigners(client: TestClient, tenant: TenantDescriptor) -> None:
    unit = make_org_unit(tenant, "COMMITTEE", "Catechism Committee")
    target = make_user(tenant, "GENERAL_MEMBER")
    sec = login(client, make_user(tenant, "COMMITTEE_SECRETARY", unit=unit))
    r = client.get(f"/api/v1/users/lookup?q={target.username}", headers=sec)
    assert r.status_code == 200 and r.json()[0]["id"] == target.public_id
    member = login(client, make_user(tenant, "GENERAL_MEMBER"))
    assert client.get(f"/api/v1/users/lookup?q={target.username}", headers=member).status_code == 403


def test_pdf_footer_escaping() -> None:
    """The parish name sits inside a CSS string in the PDF footer: no HTML entities, no breaking out."""
    from app.common.exports import _jinja_env

    t = _jinja_env().from_string("{{ x|css_string }}")
    assert t.render(x="St. Mary's Church") == "St. Mary's Church"
    assert "<" not in t.render(x='A"</style>') and '"' not in t.render(x='A"</style>')

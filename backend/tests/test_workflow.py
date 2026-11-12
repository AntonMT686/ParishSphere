"""Workflow engine test matrix (T10)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from itertools import count
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.common.ratelimit import counter
from app.core.errors import AppError
from app.db.base import utcnow
from app.db.tenant import TenantDescriptor, tenant_session_scope
from app.modules.core.models import AuditLog, Setting
from app.modules.identity.models import User
from app.modules.identity.service import create_user
from app.modules.notifications.models import Notification
from app.modules.org_units import service as org_svc
from app.modules.org_units.models import OrgUnit
from app.modules.rbac.service import assign_role, role_by_code
from app.modules.workflow import registry
from app.modules.workflow import service as wf
from app.modules.workflow.models import WorkflowDefinition, WorkflowInstance, WorkflowTask
from app.modules.workflow.registry import WorkflowHandler, register_handler, unregister_handler
from tests.conftest import auth, make_org_unit

HOST = {"Host": "wfl.parishsphere.test"}
PW = "Gl0ria-in-Excelsis"
_n = count(1)
_prio = count(500)
_entity = count(1)


def _provision(code: str, name: str) -> TenantDescriptor:
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code=code, name=name))
        s.commit()
    return provision_parish(code)


@pytest.fixture(scope="module")
def tenant(master_db: None) -> TenantDescriptor:
    return _provision("WFL", "Holy Family Church")


@pytest.fixture(autouse=True)
def calls(tenant: TenantDescriptor) -> Iterator[list[tuple[str, str]]]:
    """Record handler callbacks; afterwards switch off every workflow a test defined."""
    counter().reset()
    seen: list[tuple[str, str]] = []
    previous = {k: registry._HANDLERS.get(k) for k in ("ACTIVITY", "FIN_TRANSACTION", "FIN_PERIOD")}
    # Engine tests use made-up records: the real finance handlers would look them up.
    for k in ("FIN_TRANSACTION", "FIN_PERIOD"):
        register_handler(k, WorkflowHandler())

    def cb(name: str):  # type: ignore[no-untyped-def]
        return lambda _db, inst: seen.append((name, inst.entity_id))

    register_handler(
        "ACTIVITY",
        WorkflowHandler(
            on_submitted=cb("submitted"),
            on_approved=cb("approved"),
            on_rejected=cb("rejected"),
            on_rework=cb("rework"),
            on_withdrawn=cb("withdrawn"),
        ),
    )
    yield seen
    for k, h in previous.items():
        unregister_handler(k)
        if h is not None:
            register_handler(k, h)
    with tenant_session_scope(tenant) as s:
        s.execute(
            update(WorkflowDefinition).where(WorkflowDefinition.is_system.is_(False)).values(is_active=False)
        )
        s.execute(
            update(WorkflowInstance).where(WorkflowInstance.status.in_(wf.ACTIVE)).values(status="CANCELLED")
        )


# ----------------------------------------------------------------------------- helpers
def make_user(tenant: TenantDescriptor, *roles: str, org_unit_id: int | None = None) -> User:
    username = f"w{next(_n)}"
    with tenant_session_scope(tenant) as s:
        u = create_user(
            s, username=username, full_name=f"Person {username}", password=PW, must_change_password=False
        )
        for code in roles:
            r = role_by_code(s, code)
            assert r
            assign_role(s, u, r, org_unit_id=org_unit_id)
        s.flush()
        s.expunge(u)
    return u


def login(client: TestClient, user: User) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": user.username, "password": PW}, headers=HOST)
    assert r.status_code == 200, r.text
    return {**HOST, **auth(r.json()["access_token"])}


def users_rule(*users: User) -> list[dict[str, Any]]:
    return [{"type": "USER", "user_id": u.public_id} for u in users]


def st(name: str, *users: User, **kw: Any) -> dict[str, Any]:
    return {"key": name.lower().replace(" ", "_"), "name": name, "kind": kw.pop("kind", "REVIEW"),
            "quorum": kw.pop("quorum", "ANY"),
            "assignees": kw.pop("assignees", users_rule(*users)), **kw}  # fmt: skip


def define(tenant: TenantDescriptor, *stages: dict[str, Any], entity_type: str = "ACTIVITY",
           conditions: dict[str, Any] | None = None, priority: int | None = None) -> str:  # fmt: skip
    with tenant_session_scope(tenant) as s:
        d = WorkflowDefinition(
            code=f"T{next(_n)}", version=1, entity_type=entity_type, name="Test workflow",
            priority=priority if priority is not None else next(_prio),
            conditions=conditions or {}, stages=list(stages),
        )  # fmt: skip
        s.add(d)
        s.flush()
        return d.public_id


def submit(tenant: TenantDescriptor, user: User, entity_type: str = "ACTIVITY", **kw: Any) -> str:
    with tenant_session_scope(tenant) as s:
        inst = wf.submit(
            s, tenant, entity_type=entity_type, entity_id=kw.pop("entity_id", f"E{next(_entity)}"),
            title=kw.pop("title", "Youth retreat"), actor_id=user.id, **kw,
        )  # fmt: skip
        return inst.public_id


def act(tenant: TenantDescriptor, user: User, inst_id: str, action: str = "APPROVE",
        comment: str | None = None,
        **kw: Any) -> WorkflowInstance:  # fmt: skip
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == inst_id))
        assert inst
        task = next(t for t in inst.tasks if t.status == "PENDING" and t.assignee_id == user.id)
        out = wf.act(s, tenant, task.public_id, user.id, action, comment, **kw)
        s.flush()
        s.expunge_all()
        return out


def state(tenant: TenantDescriptor, inst_id: str) -> tuple[str, int, int, dict[str, set[int]]]:
    """(status, cycle, stage index, {task status: assignee ids of the current cycle})."""
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == inst_id))
        assert inst
        tasks: dict[str, set[int]] = {}
        for t in inst.tasks:
            if t.cycle == inst.cycle:
                tasks.setdefault(t.status, set()).add(t.assignee_id)
        return inst.status, inst.cycle, inst.stage_index, tasks


def pending(tenant: TenantDescriptor, inst_id: str) -> set[int]:
    return state(tenant, inst_id)[3].get("PENDING", set())


def notifications(tenant: TenantDescriptor, user: User, event: str) -> int:
    with tenant_session_scope(tenant) as s:
        return len(s.scalars(select(Notification).where(Notification.user_id == user.id,
                                                        Notification.event_code == event)).all())  # fmt: skip


def raises(code: str, fn, *a: Any, **kw: Any) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AppError) as e:
        fn(*a, **kw)
    assert e.value.code == code, e.value.code


# ============================================================================ engine
def test_sequential_stages_any_quorum_and_handlers(tenant: TenantDescriptor, calls: list) -> None:
    sub, a, b, c = (make_user(tenant) for _ in range(4))
    define(tenant, st("Review", a, b), st("Approve", c, kind="APPROVE"))
    iid = submit(tenant, sub, entity_id="ACT-1")
    assert pending(tenant, iid) == {a.id, b.id}
    assert notifications(tenant, a, "review.pending") == 1
    act(tenant, a, iid)
    status, _, idx, tasks = state(tenant, iid)
    assert (status, idx) == ("IN_PROGRESS", 1)
    assert tasks["CANCELLED"] == {b.id} and tasks["PENDING"] == {c.id}  # ANY: one review is enough
    assert notifications(tenant, c, "approval.pending") == 1
    act(tenant, c, iid, comment="Well planned")
    assert state(tenant, iid)[0] == "APPROVED"
    assert calls == [("submitted", "ACT-1"), ("approved", "ACT-1")]
    assert notifications(tenant, sub, "workflow.approved") == 1
    # A finished record can be submitted again (e.g. a later revision).
    submit(tenant, sub, entity_id="ACT-1")
    raises("ALREADY_SUBMITTED", submit, tenant, sub, entity_id="ACT-1")


def test_parallel_all_and_n_of_m_quorum(tenant: TenantDescriptor) -> None:
    sub, a, b, c = (make_user(tenant) for _ in range(4))
    define(tenant, st("Officers", a, b, quorum="ALL"), st("Committee", a, b, c, quorum=2))
    iid = submit(tenant, sub)
    act(tenant, a, iid)
    assert state(tenant, iid)[2] == 0 and pending(tenant, iid) == {b.id}  # ALL: still waiting for b
    act(tenant, b, iid)
    assert state(tenant, iid)[2] == 1 and pending(tenant, iid) == {a.id, b.id, c.id}
    act(tenant, c, iid)
    assert state(tenant, iid)[0] == "IN_PROGRESS"
    act(tenant, a, iid)
    status, _, _, tasks = state(tenant, iid)
    assert status == "APPROVED" and tasks["CANCELLED"] == {b.id}


def test_reject_requires_comment_and_ends(tenant: TenantDescriptor, calls: list) -> None:
    sub, a, b = (make_user(tenant) for _ in range(3))
    define(tenant, st("Review", a), st("Approve", b))
    iid = submit(tenant, sub, entity_id="ACT-R")
    raises("COMMENT_REQUIRED", act, tenant, a, iid, "REJECT")
    act(tenant, a, iid, "REJECT", "Budget missing")
    status, _, _, tasks = state(tenant, iid)
    assert status == "REJECTED" and "PENDING" not in tasks
    assert ("rejected", "ACT-R") in calls
    assert notifications(tenant, sub, "workflow.rejected") == 1
    with tenant_session_scope(tenant) as s:
        raises("TASK_NOT_PENDING", wf.act, s, tenant, task_of(tenant, iid, a), a.id, "APPROVE")


def task_of(tenant: TenantDescriptor, iid: str, user: User) -> str:
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == iid))
        assert inst
        return next(t for t in inst.tasks if t.assignee_id == user.id).public_id


def test_return_rework_and_resubmit_new_cycle(tenant: TenantDescriptor, calls: list) -> None:
    sub, a, b = (make_user(tenant) for _ in range(3))
    define(tenant, st("Review", a), st("Approve", b))
    iid = submit(tenant, sub, entity_id="ACT-W")
    act(tenant, a, iid)
    act(tenant, b, iid, "RETURN", "Add the photos")
    status, cycle, _, _ = state(tenant, iid)
    assert (status, cycle) == ("REWORK", 1)
    assert ("rework", "ACT-W") in calls and notifications(tenant, sub, "workflow.returned") == 1
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == iid))
        raises("NOT_SUBMITTER", wf.resubmit, s, tenant, inst, a.id)
        wf.resubmit(s, tenant, inst, sub.id, "Photos added", title="Youth retreat (revised)")
    status, cycle, idx, tasks = state(tenant, iid)
    assert (status, cycle, idx) == ("IN_PROGRESS", 2, 0) and tasks == {
        "PENDING": {a.id}
    }  # restarts at stage 1
    assert calls.count(("submitted", "ACT-W")) == 2
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == iid))
        assert inst and inst.title == "Youth retreat (revised)"
        assert [a.action for a in inst.actions] == ["SUBMIT", "APPROVE", "RETURN", "RESUBMIT"]
        assert len([t for t in inst.tasks if t.cycle == 1]) == 2  # history of cycle 1 kept


def test_withdraw_only_by_submitter(tenant: TenantDescriptor, calls: list) -> None:
    sub, a = make_user(tenant), make_user(tenant)
    define(tenant, st("Review", a))
    iid = submit(tenant, sub, entity_id="ACT-X")
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == iid))
        raises("NOT_SUBMITTER", wf.withdraw, s, tenant, inst, a.id)
        wf.withdraw(s, tenant, inst, sub.id, "Postponed")
    status, _, _, tasks = state(tenant, iid)
    assert status == "CANCELLED" and tasks == {"CANCELLED": {a.id}} and ("withdrawn", "ACT-X") in calls


def test_only_assignee_acts_admin_override(tenant: TenantDescriptor) -> None:
    sub, a, outsider = (make_user(tenant) for _ in range(3))
    define(tenant, st("Review", a))
    iid = submit(tenant, sub)
    task_id = task_of(tenant, iid, a)
    with tenant_session_scope(tenant) as s:
        raises("NOT_ASSIGNEE", wf.act, s, tenant, task_id, outsider.id, "APPROVE")
    with tenant_session_scope(tenant) as s:
        wf.act(s, tenant, task_id, outsider.id, "APPROVE", "Fr. is away", override=True)
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == iid))
        assert inst and inst.status == "APPROVED"
        a_ = next(x for x in inst.actions if x.action == "APPROVE")
        assert a_.actor_id == outsider.id and a_.on_behalf_of_id == a.id


def test_self_approval_optional_skip_and_admin_fallback(tenant: TenantDescriptor) -> None:
    sub, b = make_user(tenant), make_user(tenant)
    admin = make_user(tenant, "PARISH_ADMIN")
    define(tenant, st("Own org", sub, optional=True), st("Self only", sub), st("Final", b))
    iid = submit(tenant, sub)
    with tenant_session_scope(tenant) as s:
        inst = s.scalar(select(WorkflowInstance).where(WorkflowInstance.public_id == iid))
        assert inst and [a.action for a in inst.actions] == ["SUBMIT", "SKIP", "FALLBACK"]
    assert admin.id in pending(tenant, iid) and sub.id not in pending(tenant, iid)
    # Allowed by setting → the submitter decides their own stage.
    with tenant_session_scope(tenant) as s:
        s.get(Setting, "workflow.allow_self_approval").value = True  # type: ignore[union-attr]
    try:
        iid2 = submit(tenant, sub)
        assert pending(tenant, iid2) == {sub.id}
    finally:
        with tenant_session_scope(tenant) as s:
            s.get(Setting, "workflow.allow_self_approval").value = False  # type: ignore[union-attr]


def test_required_stage_without_anyone_blocks(tenant: TenantDescriptor) -> None:
    sub = make_user(tenant)
    define(tenant, st("Ghost", assignees=[{"type": "ROLE", "role": "APPROVER", "scope": "PARISH"}]))
    with tenant_session_scope(tenant) as s:
        admins = wf._role_holders(s, "PARISH_ADMIN", None)
    if not admins:
        raises("NO_APPROVER", submit, tenant, sub)
    else:
        iid = submit(tenant, sub)
        assert pending(tenant, iid) <= admins


def test_standing_and_task_delegation(tenant: TenantDescriptor) -> None:
    sub, priest, assistant, deacon = (make_user(tenant) for _ in range(4))
    define(tenant, st("Approve", priest, kind="APPROVE"), st("No delegation", deacon, allow_delegation=False))
    with tenant_session_scope(tenant) as s:
        from app.modules.workflow.models import WorkflowDelegation

        s.add(WorkflowDelegation(delegator_id=priest.id, delegate_id=assistant.id, valid_from=date.today(),
                                 valid_to=date.today() + timedelta(days=7),
                                 entity_types=["ACTIVITY"]))  # fmt: skip
    iid = submit(tenant, sub)
    assert pending(tenant, iid) == {assistant.id}
    with tenant_session_scope(tenant) as s:
        task = s.scalar(select(WorkflowTask).where(WorkflowTask.assignee_id == assistant.id))
        assert task and task.delegated_from_id == priest.id
    # The assistant hands the task to the deacon for this one record.
    act(tenant, assistant, iid, "DELEGATE", delegate_to=deacon.id)
    assert pending(tenant, iid) == {deacon.id} and state(tenant, iid)[3]["DELEGATED"] == {assistant.id}
    raises("SELF_APPROVAL", act, tenant, deacon, iid, "DELEGATE", delegate_to=sub.id)
    act(tenant, deacon, iid)
    raises("DELEGATION_NOT_ALLOWED", act, tenant, deacon, iid, "DELEGATE", delegate_to=assistant.id)
    act(tenant, deacon, iid)
    assert state(tenant, iid)[0] == "APPROVED"


def test_sla_reminder_and_escalation(tenant: TenantDescriptor) -> None:
    sub, slow, boss = (make_user(tenant) for _ in range(3))
    define(tenant, st("Review", slow, sla_hours=24, escalate_to=users_rule(boss)), st("Final", slow))
    iid = submit(tenant, sub)
    with tenant_session_scope(tenant) as s:
        assert wf.process_overdue(s, tenant) == {"reminded": 0, "escalated": 0}
        later = utcnow() + timedelta(hours=25)
        r = wf.process_overdue(s, tenant, later)
        assert r["escalated"] == 1 and r["reminded"] >= 1
        # Same day again: no second reminder for the same task, no second escalation.
        again = wf.process_overdue(s, tenant, later + timedelta(hours=1))
        assert again == {"reminded": 0, "escalated": 0}
    assert notifications(tenant, slow, "workflow.reminder") == 1
    assert pending(tenant, iid) == {slow.id, boss.id}
    act(tenant, boss, iid)  # the escalation approver decides the stage
    status, _, idx, tasks = state(tenant, iid)
    assert idx == 1 and tasks["PENDING"] == {slow.id}


def test_definition_selection(tenant: TenantDescriptor) -> None:
    sub, small, big, anb = (make_user(tenant) for _ in range(4))
    base = next(_prio) + 100
    define(tenant, st("Small", small), entity_type="FIN_TRANSACTION", priority=base)
    define(tenant, st("Big", big), entity_type="FIN_TRANSACTION", priority=base + 1,
           conditions={"min_amount": 50000})  # fmt: skip
    define(tenant, st("Anbiyam", anb), entity_type="FIN_TRANSACTION", priority=base + 1,
           conditions={"min_amount": 50000, "org_unit_types": ["ANBIYAM"]})  # fmt: skip
    unit = make_org_unit(tenant, "ANBIYAM")
    assert pending(tenant, submit(tenant, sub, "FIN_TRANSACTION", context={"amount": 1200})) == {small.id}
    assert pending(tenant, submit(tenant, sub, "FIN_TRANSACTION", context={"amount": 75000})) == {big.id}
    # Equal priority: the definition matching more conditions wins.
    iid = submit(tenant, sub, "FIN_TRANSACTION", org_unit_id=unit, context={"amount": 90000})
    assert pending(tenant, iid) == {anb.id}
    # Nothing configured for this kind of record.
    with tenant_session_scope(tenant) as s:
        s.execute(update(WorkflowDefinition).where(WorkflowDefinition.entity_type == "FIN_PERIOD")
                  .values(is_active=False))  # fmt: skip
    try:
        raises("NO_WORKFLOW_CONFIGURED", submit, tenant, sub, "FIN_PERIOD")
    finally:
        with tenant_session_scope(tenant) as s:
            s.execute(update(WorkflowDefinition).where(WorkflowDefinition.entity_type == "FIN_PERIOD")
                      .values(is_active=True))  # fmt: skip


def test_position_and_role_scoped_assignees(tenant: TenantDescriptor) -> None:
    sub = make_user(tenant)
    parent = make_org_unit(tenant, "COMMITTEE", "Finance Committee")
    child = make_org_unit(tenant, "COMMITTEE", "Building Sub-committee", parent_id=parent)
    pres, parent_pres = make_user(tenant), make_user(tenant)
    scoped = make_user(tenant, "REVIEWER", org_unit_id=parent)  # flows down to the child unit
    with tenant_session_scope(tenant) as s:
        t = org_svc.get_type(s, "COMMITTEE")
        pos = next(p for p in t.positions if p.code == "PRESIDENT")
        for unit_id, u in ((child, pres), (parent, parent_pres)):
            org_svc.appoint(s, s.get(OrgUnit, unit_id), pos, user=s.get(User, u.id), holder_name=None)  # type: ignore[arg-type]
    define(
        tenant,
        st("President", assignees=[{"type": "POSITION", "position": "PRESIDENT", "scope": "SAME_ORG_UNIT"}]),
        st(
            "Parent president",
            assignees=[{"type": "POSITION", "position": "PRESIDENT", "scope": "PARENT_ORG_UNIT"}],
        ),
        st("Scoped reviewer", assignees=[{"type": "ROLE", "role": "REVIEWER", "scope": "SAME_ORG_UNIT"}]),
    )
    iid = submit(tenant, sub, org_unit_id=child)
    assert pending(tenant, iid) == {pres.id}
    act(tenant, pres, iid)
    assert pending(tenant, iid) == {parent_pres.id}
    act(tenant, parent_pres, iid)
    assert pending(tenant, iid) == {scoped.id}


# ============================================================================ API
@pytest.fixture(scope="module")
def admin(tenant: TenantDescriptor) -> User:
    return make_user(tenant, "PARISH_ADMIN")


def test_designer_versions_keep_running_snapshot(
    client: TestClient, tenant: TenantDescriptor, admin: User
) -> None:
    h = login(client, admin)
    a, b, sub = make_user(tenant), make_user(tenant), make_user(tenant)
    body = {
        "entity_type": "ACTIVITY", "name": "Choir activities", "priority": next(_prio),
        "stages": [{"name": "Choir master", "assignees": [{"type": "USER", "user_id": a.public_id}]}],
    }  # fmt: skip
    r = client.post("/api/v1/workflow/definitions", json=body, headers=h)
    assert r.status_code == 201, r.text
    d1 = r.json()
    assert d1["version"] == 1 and d1["stages"][0]["assignees"][0]["label"] == a.full_name
    iid = submit(tenant, sub)
    assert pending(tenant, iid) == {a.id}
    body2 = {**body, "stages": [{"name": "Priest", "kind": "APPROVE",
                                 "assignees": [{"type": "USER", "user_id": b.public_id}]}]}  # fmt: skip
    body2.pop("entity_type")
    d2 = client.put(f"/api/v1/workflow/definitions/{d1['id']}", json=body2, headers=h).json()
    assert d2["version"] == 2 and d2["code"] == d1["code"] and d2["running"] == 1
    versions = client.get(f"/api/v1/workflow/definitions?code={d1['code']}", headers=h).json()
    assert [v["version"] for v in versions] == [2, 1] and not versions[1]["is_latest"]
    r = client.put(f"/api/v1/workflow/definitions/{d1['id']}", json=body2, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOT_LATEST_VERSION"
    act(tenant, a, iid)  # the running approval still follows version 1
    assert state(tenant, iid)[0] == "APPROVED"
    assert pending(tenant, submit(tenant, sub)) == {b.id}  # new submissions use version 2
    r = client.post(f"/api/v1/workflow/definitions/{d2['id']}/deactivate", headers=h)
    assert r.json()["is_active"] is False


def test_designer_validation_and_permissions(
    client: TestClient, tenant: TenantDescriptor, admin: User
) -> None:
    h = login(client, admin)
    bad_role = {"entity_type": "ACTIVITY", "name": "X workflow",
                "stages": [{"name": "S", "assignees": [{"type": "ROLE", "role": "NOPE"}]}]}  # fmt: skip
    assert client.post("/api/v1/workflow/definitions", json=bad_role, headers=h).status_code == 422
    bad_scope = {
        **bad_role,
        "stages": [{"name": "S", "assignees": [{"type": "POSITION", "position": "PRESIDENT"}]}],
    }
    assert client.post("/api/v1/workflow/definitions", json=bad_scope, headers=h).status_code == 422
    bad_type = {**bad_role, "entity_type": "PICNIC"}
    assert client.post("/api/v1/workflow/definitions", json=bad_type, headers=h).status_code == 422
    sec = login(client, make_user(tenant, "PARISH_SECRETARY"))  # has workflow.view only
    assert client.get("/api/v1/workflow/definitions", headers=sec).status_code == 200
    assert client.post("/api/v1/workflow/definitions", json=bad_role, headers=sec).status_code == 403
    member = login(client, make_user(tenant, "GENERAL_MEMBER"))
    assert client.get("/api/v1/workflow/definitions", headers=member).status_code == 403
    types = {t["code"]: t for t in client.get("/api/v1/workflow/entity-types", headers=h).json()}
    assert types["FIN_TRANSACTION"]["has_amount"] and types["ACTIVITY"]["definitions"] >= 1


def test_preview(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    h = login(client, admin)
    a = make_user(tenant)
    draft = [
        {"name": "Org president", "optional": True,
         "assignees": [{"type": "POSITION", "position": "PRESIDENT", "scope": "SAME_ORG_UNIT"}]},
        {"name": "Named", "assignees": [{"type": "USER", "user_id": a.public_id}]},
    ]  # fmt: skip
    r = client.post("/api/v1/workflow/preview", json={"entity_type": "ACTIVITY", "stages": draft}, headers=h)
    assert r.status_code == 200, r.text
    stages = r.json()["stages"]
    assert stages[0]["skipped"] is True and stages[1]["assignees"] == [
        {"name": a.full_name, "delegated_from": None}
    ]
    r = client.post("/api/v1/workflow/preview", json={"entity_type": "NOTICE"}, headers=h).json()
    assert r["definition"]["code"] == "NOTICE_DEFAULT"


def test_inbox_act_bulk_and_visibility(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    sub, rev, outsider = (make_user(tenant) for _ in range(3))
    define(tenant, st("Review", rev, sla_hours=1), st("Admin", admin))
    ids = [submit(tenant, sub, title=f"Item {i}") for i in range(3)]
    hr = login(client, rev)
    summary = client.get("/api/v1/workflow/tasks/summary", headers=hr).json()
    assert summary == {"pending": 3, "overdue": 0}
    inbox = client.get("/api/v1/workflow/tasks", headers=hr).json()
    assert inbox["total"] == 3 and inbox["items"][0]["instance"]["title"] == "Item 0"
    t0 = inbox["items"][0]["id"]
    # Reject without comment → 422; with a comment it ends the approval.
    r = client.post(f"/api/v1/workflow/tasks/{t0}/act", json={"action": "REJECT"}, headers=hr)
    assert r.status_code == 422 and r.json()["error"]["code"] == "COMMENT_REQUIRED"
    r = client.post(
        f"/api/v1/workflow/tasks/{t0}/act", json={"action": "REJECT", "comment": "Duplicate"}, headers=hr
    )
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    rest = [i["id"] for i in inbox["items"][1:]]
    r = client.post("/api/v1/workflow/tasks/bulk-approve", json={"task_ids": [*rest, t0]}, headers=hr).json()
    assert r["approved"] == rest and r["failed"][0]["code"] == "TASK_NOT_PENDING"
    assert client.get("/api/v1/workflow/tasks?state=DONE", headers=hr).json()["total"] == 3
    # Timeline / detail
    hs = login(client, sub)
    d = client.get(f"/api/v1/workflow/instances/{ids[1]}", headers=hs).json()
    assert [s["state"] for s in d["stages"]] == ["DONE", "CURRENT"] and d["pending_with"] == [admin.full_name]
    assert (
        d["can_withdraw"]
        and d["my_task"] is None
        and [a["action"] for a in d["actions"]] == ["SUBMIT", "APPROVE"]
    )
    mine = client.get("/api/v1/workflow/instances?status=ACTIVE", headers=hs).json()
    assert mine["total"] == 2
    assert (
        client.get(f"/api/v1/workflow/instances/{ids[1]}", headers=login(client, outsider)).status_code == 403
    )
    ha = login(client, admin)
    d = client.get(f"/api/v1/workflow/instances/{ids[1]}", headers=ha).json()
    assert d["my_task"] and d["can_override"]
    hist = client.get(f"/api/v1/workflow/entities/ACTIVITY/{d['entity_id']}", headers=hs).json()
    assert len(hist) == 1 and hist[0]["id"] == ids[1]
    # Withdraw through the API
    r = client.post(
        f"/api/v1/workflow/instances/{ids[2]}/withdraw", json={"comment": "Not needed"}, headers=hs
    )
    assert r.json()["status"] == "CANCELLED"


def test_admin_override_is_audited(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    sub, rev = make_user(tenant), make_user(tenant)
    define(tenant, st("Review", rev))
    iid = submit(tenant, sub)
    with tenant_session_scope(tenant) as s:
        task = s.scalar(select(WorkflowTask).join(WorkflowInstance).where(WorkflowInstance.public_id == iid))
        assert task
        tid = task.public_id
    hs = login(client, make_user(tenant, "PARISH_SECRETARY"))
    assert (
        client.post(f"/api/v1/workflow/tasks/{tid}/act", json={"action": "APPROVE"}, headers=hs).status_code
        == 403
    )
    r = client.post(
        f"/api/v1/workflow/tasks/{tid}/act", json={"action": "APPROVE"}, headers=login(client, admin)
    )
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    with tenant_session_scope(tenant) as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == "OVERRIDE", AuditLog.entity_id == tid))


def test_delegation_api(client: TestClient, tenant: TenantDescriptor, admin: User) -> None:
    me, other, third = (make_user(tenant) for _ in range(3))
    h = login(client, me)
    r = client.post("/api/v1/workflow/delegations", json={"delegate_user_id": me.public_id}, headers=h)
    assert r.status_code == 422
    r = client.post("/api/v1/workflow/delegations",
                    json={"delegate_user_id": other.public_id, "reason": "Retreat"}, headers=h)  # fmt: skip
    assert r.status_code == 201 and r.json()["active"] is True
    did = r.json()["id"]
    # Someone else's delegation needs workflow.manage.
    r = client.post("/api/v1/workflow/delegations",
                    json={"delegate_user_id": third.public_id, "delegator_user_id": other.public_id},
                    headers=h)  # fmt: skip
    assert r.status_code == 403
    assert [
        d["id"] for d in client.get("/api/v1/workflow/delegations", headers=login(client, other)).json()
    ] == [did]
    assert client.get("/api/v1/workflow/delegations?all=true", headers=h).status_code == 403
    assert client.post(f"/api/v1/workflow/delegations/{did}/end", headers=h).json()["active"] is False


# ============================================================================ seeded defaults
def test_seeded_activity_workflow_end_to_end(master_db: None) -> None:
    t = _provision("WFS", "St. Anthony's Church")
    with tenant_session_scope(t) as s:
        codes = set(s.scalars(select(WorkflowDefinition.code)))
    assert codes == {"ACTIVITY_DEFAULT", "MINUTES_DEFAULT", "FIN_TXN_DEFAULT", "FIN_TXN_LARGE",
                     "FIN_PERIOD_DEFAULT", "NOTICE_DEFAULT"}  # fmt: skip
    society = make_org_unit(t, "SOCIETY", "Youth Society")
    secretary_of_society = make_user(t)
    president = make_user(t)
    parish_secretary = make_user(t, "PARISH_SECRETARY")
    priest = make_user(t, "PARISH_PRIEST")
    with tenant_session_scope(t) as s:
        pos = next(p for p in org_svc.get_type(s, "SOCIETY").positions if p.code == "PRESIDENT")
        org_svc.appoint(s, s.get(OrgUnit, society), pos, user=s.get(User, president.id), holder_name=None)  # type: ignore[arg-type]
    iid = submit(t, secretary_of_society, org_unit_id=society)
    for reviewer in (president, parish_secretary, priest):
        assert pending(t, iid) == {reviewer.id}
        act(t, reviewer, iid)
    assert state(t, iid)[0] == "APPROVED"
    # A parish-level activity skips the organisation president.
    iid = submit(t, parish_secretary)
    assert pending(t, iid) == {priest.id}  # secretary is the submitter → their own stage is skipped
    # Large transactions need both council officers.
    president_role = make_user(t, "PARISH_PRESIDENT")
    treasurer = make_user(t, "PARISH_TREASURER")
    iid = submit(t, make_user(t), "FIN_TRANSACTION", context={"amount": 60000})
    act(t, treasurer, iid)
    assert pending(t, iid) == {president_role.id, parish_secretary.id}

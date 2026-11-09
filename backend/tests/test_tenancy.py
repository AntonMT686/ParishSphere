"""Tenant resolution, provisioning, migration and isolation tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.tenant import tenant_session_scope
from app.modules.core.models import Sequence, Setting
from app.tenancy.resolver import extract_subdomain, resolve_tenant


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("stmarys.parishsphere.test", "stmarys"),
        ("StMarys.ParishSphere.test:8443", "stmarys"),
        ("parishsphere.test", None),
        ("www.parishsphere.test", None),
        ("a.b.parishsphere.test", None),
        ("evil.com", None),
        ("stmarys.parishsphere.test.evil.com", None),
        (None, None),
    ],
)
def test_extract_subdomain(app, host: str | None, expected: str | None) -> None:  # type: ignore[no-untyped-def]
    assert extract_subdomain(host) == expected


def test_provisioning_creates_seeded_databases(two_parishes: tuple[str, str]) -> None:
    for code in two_parishes:
        tenant = resolve_tenant(code=code)
        assert tenant is not None and tenant.status == "ACTIVE"
        with tenant_session_scope(tenant) as s:
            assert s.get(Setting, "parish.code").value == code  # type: ignore[union-attr]
            assert s.get(Sequence, "FAMILY") is not None


def test_provisioning_is_idempotent(two_parishes: tuple[str, str]) -> None:
    from app.tenancy.provisioning import provision_parish

    provision_parish(two_parishes[0])
    tenant = resolve_tenant(code=two_parishes[0])
    assert tenant is not None
    with tenant_session_scope(tenant) as s:
        assert len([q for q in s.scalars(select(Sequence)) if ":" not in q.name]) == 7


def test_tenant_databases_are_isolated(two_parishes: tuple[str, str]) -> None:
    a, b = (resolve_tenant(code=c) for c in two_parishes)
    assert a and b and a.db_name != b.db_name
    with tenant_session_scope(a) as s:
        s.add(Setting(key="isolation.probe", value="only-in-a"))
    with tenant_session_scope(b) as s:
        assert s.get(Setting, "isolation.probe") is None
    with tenant_session_scope(a) as s:
        assert s.get(Setting, "isolation.probe").value == "only-in-a"  # type: ignore[union-attr]


def test_branding_resolved_by_subdomain(client: TestClient, two_parishes: tuple[str, str]) -> None:
    r = client.get("/api/v1/tenant/branding", headers={"Host": "stmarys.parishsphere.test"})
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "STMARYS"
    r = client.get("/api/v1/tenant/branding", headers={"Host": "holycross.parishsphere.test"})
    assert r.json()["code"] == "HOLYCROSS"
    assert r.json()["diocese_name"] == "Madurai Diocese"


def test_branding_resolved_by_header(client: TestClient, two_parishes: tuple[str, str]) -> None:
    r = client.get("/api/v1/tenant/branding", headers={"X-Parish-Code": "holycross"})
    assert r.status_code == 200
    assert r.json()["name"] == "Holy Cross Church"


def test_subdomain_takes_precedence_over_header(client: TestClient, two_parishes: tuple[str, str]) -> None:
    r = client.get(
        "/api/v1/tenant/branding",
        headers={"Host": "stmarys.parishsphere.test", "X-Parish-Code": "HOLYCROSS"},
    )
    assert r.json()["code"] == "STMARYS"


def test_unknown_or_missing_tenant(client: TestClient, two_parishes: tuple[str, str]) -> None:
    r = client.get("/api/v1/tenant/branding", headers={"Host": "nope.parishsphere.test"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TENANT_NOT_FOUND"
    r = client.get("/api/v1/tenant/branding")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TENANT_NOT_IDENTIFIED"


def test_migrate_all_tenants(two_parishes: tuple[str, str]) -> None:
    from app.db.migrations import head_revision
    from app.tenancy.provisioning import migrate_all_tenants

    results = migrate_all_tenants(parallel=2)
    assert {r.code for r in results} >= set(two_parishes)
    assert all(r.ok and r.revision == head_revision("tenant") for r in results)


def test_engine_registry_lru_eviction(two_parishes: tuple[str, str]) -> None:
    from app.db.tenant import EngineRegistry

    reg = EngineRegistry(max_size=1)
    a, b = (resolve_tenant(code=c) for c in two_parishes)
    assert a and b
    reg.engine(a)
    reg.engine(b)
    assert len(reg) == 1 and b.code in reg and a.code not in reg
    reg.dispose_all()

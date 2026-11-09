"""Test fixtures.

Tests run against SQLite files (one per tenant) so they need no external services; CI also runs
them against MySQL by setting ``PS_TEST_MYSQL_URL`` (see docs/09-roadmap-and-testing.md).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def _env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    data_dir = tmp_path_factory.mktemp("psdata")
    os.environ.update(
        {
            "PS_ENV": "test",
            "PS_MASTER_DATABASE_URL": f"sqlite:///{data_dir / 'ps_master.db'}",
            "PS_TENANT_DB_DRIVER": "sqlite",
            "PS_SQLITE_DATA_DIR": str(data_dir),
            "PS_BASE_DOMAIN": "parishsphere.test",
            "PS_REDIS_URL": "",
            "PS_LOG_LEVEL": "WARNING",
        }
    )
    os.environ.pop("PS_REDIS_URL")
    from app.core.config import get_settings
    from app.db.master import reset_master_engine
    from app.db.tenant import reset_engine_registry
    from app.tenancy.resolver import reset_tenant_cache

    get_settings.cache_clear()
    reset_master_engine()
    reset_engine_registry()
    reset_tenant_cache()
    yield data_dir
    reset_engine_registry()
    reset_master_engine()


@pytest.fixture(scope="session")
def master_db(_env: Path) -> None:
    from app.db import migrations
    from app.db.master import get_master_engine, master_session
    from app.master.auth import create_platform_user
    from app.master.models import Diocese

    migrations.upgrade(get_master_engine(), "master")
    with master_session() as s:
        create_platform_user(
            s, email="root@parishsphere.org", full_name="Root", password="Sup3r-secret!", is_super_admin=True
        )
        create_platform_user(
            s, email="viewer@parishsphere.org", full_name="Viewer", password="Vi3wer-secret!"
        )
        s.add_all([Diocese(code="CHN", name="Chennai Diocese"), Diocese(code="MDU", name="Madurai Diocese")])
        s.commit()


@pytest.fixture(scope="session")
def app(master_db: None):  # type: ignore[no-untyped-def]
    from app.main import create_app

    return create_app()


@pytest.fixture()
def client(app) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(app)


@pytest.fixture(scope="session")
def two_parishes(master_db: None) -> tuple[str, str]:
    """Provision two parishes in different dioceses (session-scoped; provisioning is slow)."""
    from app.db.master import master_session
    from app.tenancy.provisioning import ParishRegistration, provision_parish, register_parish

    with master_session() as s:
        register_parish(s, ParishRegistration(diocese_code="CHN", code="STMARYS", name="St. Mary's Church"))
        register_parish(
            s,
            ParishRegistration(
                diocese_code="MDU", code="HOLYCROSS", name="Holy Cross Church", subdomain="holycross"
            ),
        )
        s.commit()
    provision_parish("STMARYS")
    provision_parish("HOLYCROSS")
    return "STMARYS", "HOLYCROSS"


@pytest.fixture()
def super_token(client: TestClient) -> str:
    r = client.post(
        "/api/v1/platform/auth/login", json={"email": "root@parishsphere.org", "password": "Sup3r-secret!"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_org_unit(
    tenant, type_code: str = "COMMITTEE", name: str | None = None, parent_id: int | None = None
) -> int:  # type: ignore[no-untyped-def]
    """Create an organisation unit directly in a parish DB and return its internal id."""
    from itertools import count

    from app.db.tenant import tenant_session_scope
    from app.modules.org_units import service
    from app.modules.org_units.models import OrgUnit

    seq = make_org_unit.__dict__.setdefault("_seq", count(1))
    with tenant_session_scope(tenant) as s:
        t = service.get_type(s, type_code)
        u = OrgUnit(
            type_id=t.id, parent_id=parent_id, code=f"T{next(seq):05d}", name=name or f"{t.name} unit"
        )
        s.add(u)
        s.flush()
        return u.id

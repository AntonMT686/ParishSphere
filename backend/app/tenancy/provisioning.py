"""Parish provisioning and cross-tenant migration orchestration.

Provisioning steps (idempotent – a failed run may simply be re-executed):

1. ensure ``parishes`` + ``tenant_databases`` + ``tenant_settings`` rows exist (status PROVISIONING)
2. create the physical database (and a dedicated DB user when credentials are not shared)
3. run tenant Alembic migrations to head
4. run seeders (settings, sequences, roles, org unit types, workflows …)
5. mark the parish ACTIVE and record ``schema_version``
"""

from __future__ import annotations

import multiprocessing
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import decrypt_secret, encrypt_secret, generate_token
from app.db import migrations
from app.db.base import utcnow
from app.db.master import master_session
from app.db.tenant import TenantDescriptor, get_engine_registry, tenant_session_scope
from app.master.models import Diocese, Parish, ParishStatus, TenantDatabase, TenantSettings
from app.tenancy.dbadmin import get_db_admin
from app.tenancy.resolver import descriptor_from_parish, invalidate_tenant
from app.tenancy.seed import run_seeders

log = structlog.get_logger(__name__)

CODE_RE = re.compile(r"^[A-Z0-9]{2,20}$")
SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


@dataclass
class ParishRegistration:
    diocese_code: str
    code: str
    name: str
    subdomain: str | None = None
    established_on: date | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    email: str | None = None
    language: str = "en"
    currency: str = "INR"
    fy_start_month: int = 4
    extra_seed_context: dict[str, Any] = field(default_factory=dict)


def tenant_db_name(code: str) -> str:
    return f"{get_settings().tenant_db_name_prefix}{code.lower()}"


def validate_registration(reg: ParishRegistration) -> None:
    errors: list[dict[str, str]] = []
    reg.code = reg.code.strip().upper()
    reg.subdomain = (reg.subdomain or reg.code).strip().lower()
    if not CODE_RE.match(reg.code):
        errors.append({"field": "code", "message": "2-20 uppercase letters or digits"})
    if not SUBDOMAIN_RE.match(reg.subdomain) or reg.subdomain in get_settings().reserved_subdomains:
        errors.append({"field": "subdomain", "message": "Invalid or reserved subdomain"})
    if not 1 <= reg.fy_start_month <= 12:
        errors.append({"field": "fy_start_month", "message": "Must be between 1 and 12"})
    if errors:
        raise ValidationFailed(details=errors)


def register_parish(session: Session, reg: ParishRegistration, actor_id: int | None = None) -> Parish:
    """Create (or return the existing PROVISIONING/FAILED) master rows for a parish."""
    validate_registration(reg)
    diocese = session.scalars(
        select(Diocese).where(Diocese.code == reg.diocese_code.upper(), Diocese.is_deleted.is_(False))
    ).first()
    if diocese is None:
        raise NotFound("Diocese not found", code="DIOCESE_NOT_FOUND")

    existing = session.scalars(
        select(Parish).options(joinedload(Parish.database)).where(Parish.code == reg.code)
    ).first()
    if existing is not None:
        if existing.status in (ParishStatus.PROVISIONING, ParishStatus.FAILED):
            return existing
        raise Conflict("A parish with this code already exists", code="PARISH_CODE_EXISTS")
    if session.scalars(select(Parish.id).where(Parish.subdomain == reg.subdomain)).first() is not None:
        raise Conflict("Subdomain already in use", code="SUBDOMAIN_EXISTS")

    settings = get_settings()
    parish = Parish(
        diocese_id=diocese.id,
        code=reg.code,
        subdomain=reg.subdomain,  # type: ignore[arg-type]
        name=reg.name,
        status=ParishStatus.PROVISIONING,
        established_on=reg.established_on,
        address_line1=reg.address_line1,
        city=reg.city,
        state=reg.state,
        postal_code=reg.postal_code,
        phone=reg.phone,
        email=reg.email,
        created_by=actor_id,
    )
    session.add(parish)
    session.flush()
    db_user: str | None = None
    db_password_enc: bytes | None = None
    if not settings.tenant_db_shared_credentials and settings.tenant_db_driver == "mysql":
        db_user = f"pst_{reg.code.lower()}"[:32]
        db_password_enc = encrypt_secret(generate_token(24))
    session.add(
        TenantDatabase(
            parish_id=parish.id,
            db_host=settings.tenant_db_host,
            db_port=settings.tenant_db_port,
            db_name=tenant_db_name(reg.code),
            db_user=db_user,
            db_password_enc=db_password_enc,
        )
    )
    session.add(
        TenantSettings(
            parish_id=parish.id,
            display_name=reg.name,
            default_language=reg.language,
            currency=reg.currency,
            fy_start_month=reg.fy_start_month,
        )
    )
    session.flush()
    session.refresh(parish)
    return parish


def _load_parish(session: Session, code: str) -> Parish:
    parish = session.scalars(
        select(Parish)
        .options(joinedload(Parish.database), joinedload(Parish.diocese), joinedload(Parish.settings))
        .where(Parish.code == code.upper())
    ).first()
    if parish is None or parish.database is None:
        raise NotFound("Parish not found", code="TENANT_NOT_FOUND")
    return parish


def migrate_tenant(tenant: TenantDescriptor) -> str | None:
    engine = get_engine_registry().engine(tenant)
    return migrations.upgrade(engine, "tenant")


def provision_parish(code: str, seed_context: dict[str, Any] | None = None) -> TenantDescriptor:
    """Create the physical DB, migrate and seed it, then activate the parish. Idempotent."""
    with master_session() as session:
        parish = _load_parish(session, code)
        tenant = descriptor_from_parish(parish)
        tdb = parish.database
        assert tdb is not None
        ctx: dict[str, Any] = {
            "parish_name": parish.name,
            "parish_code": parish.code,
            "fy_start_month": parish.settings.fy_start_month if parish.settings else 4,
            "currency": parish.settings.currency if parish.settings else "INR",
            "language": parish.settings.default_language if parish.settings else "en",
            **(seed_context or {}),
        }
        try:
            admin = get_db_admin(tdb.db_host, tdb.db_port)
            admin.create_database(tdb.db_name)
            if tdb.db_user and tdb.db_password_enc:
                admin.create_user(tdb.db_name, tdb.db_user, decrypt_secret(tdb.db_password_enc))
            get_engine_registry().evict(tenant.code)
            revision = migrate_tenant(tenant)
            with tenant_session_scope(tenant) as tsession:
                run_seeders(tsession, ctx)
            tdb.schema_version = revision
            tdb.last_migrated_at = utcnow()
            tdb.last_error = None
            if parish.status in (ParishStatus.PROVISIONING, ParishStatus.FAILED):
                parish.status = ParishStatus.ACTIVE
            session.commit()
        except Exception as exc:
            session.rollback()
            parish = _load_parish(session, code)
            parish.status = ParishStatus.FAILED
            assert parish.database is not None
            parish.database.last_error = str(exc)[:4000]
            session.commit()
            log.exception("provisioning_failed", parish=code)
            raise
        invalidate_tenant(parish.code, parish.subdomain)
        log.info("parish_provisioned", parish=parish.code, revision=revision)
        return descriptor_from_parish(parish)


@dataclass
class MigrationResult:
    code: str
    ok: bool
    revision: str | None = None
    error: str | None = None


def _migrate_one(t: TenantDescriptor) -> MigrationResult:
    try:
        return MigrationResult(t.code, True, migrate_tenant(t))
    except Exception as exc:
        log.exception("tenant_migration_failed", parish=t.code)
        return MigrationResult(t.code, False, error=str(exc)[:4000])


def migrate_all_tenants(only: list[str] | None = None, parallel: int = 4) -> list[MigrationResult]:
    """Upgrade every non-archived parish database to head; records results in master."""
    with master_session() as session:
        stmt = (
            select(Parish)
            .options(joinedload(Parish.database), joinedload(Parish.diocese))
            .where(Parish.status.notin_([ParishStatus.ARCHIVED, ParishStatus.PROVISIONING]))
            .where(Parish.is_deleted.is_(False))
        )
        if only:
            stmt = stmt.where(Parish.code.in_([c.upper() for c in only]))
        tenants = [
            descriptor_from_parish(p) for p in session.scalars(stmt).unique() if p.database is not None
        ]

    results: list[MigrationResult] = []
    if parallel <= 1 or len(tenants) <= 1:
        results = [_migrate_one(t) for t in tenants]
    else:
        # Alembic is not thread-safe, so tenants are migrated in separate processes.
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=min(parallel, len(tenants)), mp_context=ctx) as pool:
            futures = [pool.submit(_migrate_one, t) for t in tenants]
            results = [f.result() for f in as_completed(futures)]

    with master_session() as session:
        by_code = {r.code: r for r in results}
        for tdb in session.scalars(select(TenantDatabase).join(Parish).where(Parish.code.in_(list(by_code)))):
            r = by_code[tdb.parish.code]
            if r.ok:
                tdb.schema_version, tdb.last_migrated_at, tdb.last_error = r.revision, utcnow(), None
            else:
                tdb.last_error = r.error
        session.commit()
    return sorted(results, key=lambda r: r.code)

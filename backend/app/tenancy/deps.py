"""FastAPI dependencies for tenant-scoped routes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.context import set_tenant_code
from app.core.errors import AppError, NotFound
from app.db.tenant import TenantDescriptor, get_engine_registry
from app.tenancy.resolver import PARISH_CODE_HEADER, extract_subdomain, resolve_tenant


class TenantSuspended(AppError):
    status_code = 403
    code = "TENANT_SUSPENDED"
    message = "This parish account is not active"


def get_current_tenant(request: Request) -> TenantDescriptor:
    """Resolve the parish for this request from the Host subdomain or the X-Parish-Code header."""
    cached: TenantDescriptor | None = getattr(request.state, "tenant", None)
    if cached is not None:
        return cached
    subdomain = extract_subdomain(request.headers.get("host"))
    header_code = request.headers.get(PARISH_CODE_HEADER)
    tenant = None
    if subdomain:
        tenant = resolve_tenant(subdomain=subdomain)
    elif header_code:
        tenant = resolve_tenant(code=header_code)
    else:
        raise NotFound("Parish could not be identified from the request", code="TENANT_NOT_IDENTIFIED")
    if tenant is None:
        raise NotFound("Parish not found", code="TENANT_NOT_FOUND")
    if not tenant.is_operational:
        raise TenantSuspended()
    request.state.tenant = tenant
    set_tenant_code(tenant.code)
    return tenant


CurrentTenant = Annotated[TenantDescriptor, Depends(get_current_tenant)]


def get_tenant_session(tenant: CurrentTenant) -> Iterator[Session]:
    """Request-scoped session bound to the resolved parish database."""
    session = get_engine_registry().session(tenant)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


TenantSession = Annotated[Session, Depends(get_tenant_session)]

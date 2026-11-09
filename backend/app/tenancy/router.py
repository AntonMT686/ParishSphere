"""Public tenant endpoints (no authentication) – used by the login page to theme itself."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.master import master_session
from app.master.models import Parish
from app.master.schemas import TenantBrandingOut
from app.tenancy.deps import CurrentTenant

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("/branding", response_model=TenantBrandingOut)
def tenant_branding(tenant: CurrentTenant) -> TenantBrandingOut:
    with master_session() as session:
        parish = session.scalars(
            select(Parish)
            .options(joinedload(Parish.settings), joinedload(Parish.diocese))
            .where(Parish.id == tenant.parish_id)
        ).one()
        s = parish.settings
        return TenantBrandingOut(
            parish_id=parish.public_id,
            code=parish.code,
            name=parish.name,
            display_name=s.display_name if s else parish.name,
            logo_url=s.logo_url if s else None,
            primary_color=s.primary_color if s else None,
            default_language=s.default_language if s else "en",
            currency=s.currency if s else "INR",
            diocese_name=parish.diocese.name,
        )

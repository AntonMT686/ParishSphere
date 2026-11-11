"""Parish profile & priest services.

Assignment dates: ``appointed_on`` is the first day of service and ``relieved_on`` the handover date
(the first day the priest no longer serves), so a same-day handover needs no gap or overlap.


* The profile lives in the parish database; the pre-login branding fields are mirrored to the master
  database (``parishes`` + ``tenant_settings``) after every change.
* Priest assignments keep full history. There is at most one current Parish Priest. If the priest has a
  user account, the Parish Priest assignment grants the PARISH_PRIEST role (parish-wide) for exactly the
  period of the assignment – relieving the priest ends the role.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.storage import build_key, get_storage, validate_upload
from app.core.errors import Conflict, ValidationFailed
from app.db.base import utcnow
from app.db.master import master_session
from app.db.tenant import TenantDescriptor
from app.master.models import Parish, TenantSettings
from app.modules.identity.models import User
from app.modules.parish.models import ParishProfile, Priest, PriestAssignment
from app.modules.rbac.models import UserRoleAssignment
from app.modules.rbac.service import assign_role, role_by_code
from app.tenancy.resolver import invalidate_tenant
from app.tenancy.seed import register_seeder

PARISH_PRIEST = "PARISH_PRIEST"
ASSIGNMENT_ROLES = ("PARISH_PRIEST", "ASSISTANT_PRIEST", "RESIDENT_PRIEST", "DEACON", "OTHER")
PRIEST_STATUSES = ("ACTIVE", "RETIRED", "DECEASED", "LEFT")
LOGO_MAX_BYTES = 2 * 1024 * 1024
PROFILE_FIELDS = (
    "name",
    "name_local",
    "patron_saint",
    "established_on",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "phone",
    "email",
    "website",
    "about",
    "primary_color",
    "default_language",
    "currency",
    "timezone",
    "fy_start_month",
)


# ============================================================================ profile
@register_seeder("parish.profile", order=40)
def seed_profile(session: Session, ctx: dict[str, Any]) -> None:
    if session.get(ParishProfile, 1) is None and ctx.get("parish_name"):
        session.add(
            ParishProfile(
                id=1,
                name=ctx["parish_name"],
                fy_start_month=ctx.get("fy_start_month", 4),
                currency=ctx.get("currency", "INR"),
                default_language=ctx.get("language", "en"),
            )
        )


def get_profile(db: Session, tenant: TenantDescriptor) -> ParishProfile:
    p = db.get(ParishProfile, 1)
    if p is None:  # parishes provisioned before T9 (seeding also runs on migrate-tenants)
        p = ParishProfile(id=1, name=tenant.name)
        db.add(p)
        db.flush()
    return p


def logo_url(p: ParishProfile) -> str | None:
    return f"/api/v1/tenant/logo?v={p.logo_version}" if p.logo_key else None


def sync_to_master(tenant: TenantDescriptor, p: ParishProfile) -> None:
    """Mirror pre-login branding and directory details to the master database."""
    with master_session() as ms:
        parish = ms.get(Parish, tenant.parish_id)
        if parish is None:
            return
        for f in (
            "name",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "phone",
            "email",
            "established_on",
        ):
            setattr(parish, f, getattr(p, f))
        s = ms.get(TenantSettings, tenant.parish_id)
        if s is None:
            s = TenantSettings(parish_id=tenant.parish_id, display_name=p.name)
            ms.add(s)
        s.display_name = p.name
        s.logo_url = logo_url(p)
        s.primary_color = p.primary_color
        s.default_language = p.default_language
        s.currency = p.currency
        s.timezone = p.timezone
        s.fy_start_month = p.fy_start_month
        ms.commit()
    invalidate_tenant(tenant.code, tenant.subdomain)


def update_profile(p: ParishProfile, data: dict[str, Any], actor: int | None) -> None:
    for k, v in data.items():
        if k in PROFILE_FIELDS:
            setattr(p, k, v)
    p.updated_by = actor


def set_logo(p: ParishProfile, tenant: TenantDescriptor, filename: str, data: bytes) -> None:
    if len(data) > LOGO_MAX_BYTES:
        raise ValidationFailed("The logo must be at most 2 MB", code="FILE_TOO_LARGE")
    info = validate_upload(filename, data, allowed={"png", "jpg", "jpeg"})
    storage = get_storage()
    old = p.logo_key
    key = build_key(tenant.code, "branding", info.extension)
    storage.put(key, data, info.content_type)
    p.logo_key, p.logo_content_type = key, info.content_type
    p.logo_version += 1
    if old:
        storage.delete(old)


def remove_logo(p: ParishProfile) -> None:
    if p.logo_key:
        get_storage().delete(p.logo_key)
    p.logo_key = p.logo_content_type = None
    p.logo_version += 1


# ============================================================================ priests
def current_assignments_stmt(on: date | None = None):  # type: ignore[no-untyped-def]
    on = on or date.today()
    return select(PriestAssignment).where(
        PriestAssignment.appointed_on <= on,
        # relieved_on is the handover date: the priest serves up to, not including, that day.
        or_(PriestAssignment.relieved_on.is_(None), PriestAssignment.relieved_on > on),
    )


def current_parish_priest(db: Session, on: date | None = None) -> PriestAssignment | None:
    return db.scalars(current_assignments_stmt(on).where(PriestAssignment.role == PARISH_PRIEST)).first()


def _grant_role(db: Session, a: PriestAssignment, actor: int | None) -> None:
    """Give the linked user the PARISH_PRIEST role for the assignment period."""
    priest = a.priest
    if a.role != PARISH_PRIEST or priest.user_id is None or a.role_assignment_id is not None:
        return
    if a.relieved_on is not None and a.relieved_on <= date.today():
        return
    user = db.get(User, priest.user_id)
    role = role_by_code(db, PARISH_PRIEST)
    if user is None or role is None or not user.is_active:
        return
    existing = db.scalars(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.role_id == role.id,
            UserRoleAssignment.org_unit_id.is_(None),
            UserRoleAssignment.ended_at.is_(None),
        )
    ).first()
    if existing is not None:
        return  # role held independently – do not take ownership of it
    ra = assign_role(
        db,
        user,
        role,
        valid_from=max(a.appointed_on, date.today()),
        valid_to=a.relieved_on - timedelta(days=1) if a.relieved_on else None,
        assigned_by=actor,
        remarks=f"Parish Priest from {a.appointed_on.isoformat()}",
    )
    a.role_assignment_id = ra.id


def _end_role(db: Session, a: PriestAssignment, actor: int | None, *, now: bool = False) -> None:
    """End the role granted by this assignment: at the relieving date, or immediately (``now``)."""
    if a.role_assignment_id is None:
        return
    ra = db.get(UserRoleAssignment, a.role_assignment_id)
    if ra is not None and ra.ended_at is None:
        if now or a.relieved_on is None or a.relieved_on <= date.today():
            ra.valid_to = min(date.today(), a.relieved_on) if a.relieved_on else date.today()
            ra.ended_at, ra.ended_by = utcnow(), actor
        else:
            ra.valid_to = a.relieved_on - timedelta(days=1)  # last day of service
    if now or ra is None or ra.ended_at is not None:
        a.role_assignment_id = None


def appoint(
    db: Session,
    priest: Priest,
    *,
    role: str,
    appointed_on: date,
    relieved_on: date | None = None,
    responsibilities: str | None = None,
    appointment_ref: str | None = None,
    remarks: str | None = None,
    relieve_current: bool = False,
    actor: int | None = None,
) -> PriestAssignment:
    if role not in ASSIGNMENT_ROLES:
        raise ValidationFailed(details=[{"field": "role", "message": "Unknown role"}])
    if priest.status != "ACTIVE":
        raise Conflict("Only active priests can be appointed", code="INVALID_STATE")
    if relieved_on is not None and relieved_on <= appointed_on:
        raise ValidationFailed(
            details=[{"field": "relieved_on", "message": "Must be after the appointment date"}]
        )
    same = db.scalars(
        current_assignments_stmt(appointed_on).where(
            PriestAssignment.priest_id == priest.id, PriestAssignment.role == role
        )
    ).first()
    if same is not None:
        raise Conflict("This priest already holds this assignment", code="ALREADY_ASSIGNED")
    if role == PARISH_PRIEST:
        current = current_parish_priest(db, appointed_on)
        if current is not None:
            if not relieve_current:
                raise Conflict(
                    f"{current.priest.display_name} is the current Parish Priest; "
                    "relieve him first or confirm the transfer",
                    code="CURRENT_PARISH_PRIEST_EXISTS",
                )
            relieve(
                db,
                current,
                relieved_on=appointed_on,  # same-day handover
                reason="Succeeded by " + priest.display_name,
                actor=actor,
            )
    a = PriestAssignment(
        priest_id=priest.id,
        role=role,
        appointed_on=appointed_on,
        relieved_on=relieved_on,
        responsibilities=responsibilities,
        appointment_ref=appointment_ref,
        remarks=remarks,
        created_by=actor,
    )
    db.add(a)
    db.flush()
    db.refresh(a)
    _grant_role(db, a, actor)
    return a


def relieve(
    db: Session, a: PriestAssignment, *, relieved_on: date | None, reason: str | None, actor: int | None
) -> None:
    if a.relieved_on is not None and a.relieved_on <= date.today():
        raise Conflict("This assignment has already ended", code="INVALID_STATE")
    relieved_on = relieved_on or date.today()
    if relieved_on < a.appointed_on:
        raise ValidationFailed(
            "The relieving date is before the appointment date",
            details=[{"field": "relieved_on", "message": "Before the appointment date"}],
        )
    a.relieved_on = relieved_on
    a.relieving_reason = reason
    _end_role(db, a, actor)


def link_user(db: Session, priest: Priest, user: User | None, actor: int | None) -> None:
    """Link (or unlink) the priest's user account; moves the Parish Priest role accordingly."""
    if user is not None:
        clash = db.scalars(
            select(Priest.id).where(
                Priest.user_id == user.id, Priest.id != priest.id, Priest.is_deleted.is_(False)
            )
        ).first()
        if clash is not None:
            raise Conflict("This user is already linked to another priest", code="USER_ALREADY_LINKED")
    current = [a for a in priest.assignments if a.is_current(date.today())]
    for a in current:
        _end_role(db, a, actor, now=True)
    priest.user_id = user.id if user else None
    db.flush()
    for a in current:
        _grant_role(db, a, actor)


def set_status(db: Session, priest: Priest, status: str, actor: int | None) -> int:
    """Retiring/leaving/death relieves current assignments as of today."""
    if status not in PRIEST_STATUSES:
        raise ValidationFailed(details=[{"field": "status", "message": "Unknown status"}])
    ended = 0
    if status != "ACTIVE":
        for a in priest.assignments:
            if a.is_current(date.today()) or (a.appointed_on > date.today() and a.relieved_on is None):
                relieve(
                    db,
                    a,
                    relieved_on=max(date.today(), a.appointed_on),
                    reason=f"Priest {status.lower()}",
                    actor=actor,
                )
                ended += 1
    priest.status = status
    return ended

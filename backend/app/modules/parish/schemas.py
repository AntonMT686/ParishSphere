"""Parish profile & priest API schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

PriestRole = str  # validated in the service (PARISH_PRIEST, ASSISTANT_PRIEST, RESIDENT_PRIEST, DEACON, OTHER)


class ProfileOut(BaseModel):
    name: str
    name_local: str | None
    patron_saint: str | None
    established_on: date | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    phone: str | None
    email: str | None
    website: str | None
    about: str | None
    logo_url: str | None
    primary_color: str | None
    default_language: str
    currency: str
    timezone: str
    fy_start_month: int
    code: str
    diocese_name: str
    parish_priest: str | None
    updated_at: datetime


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    patron_saint: str | None = Field(default=None, max_length=200)
    established_on: date | None = None
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    website: str | None = Field(default=None, max_length=255, pattern=r"^https?://\S+$")
    about: str | None = Field(default=None, max_length=5000)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    default_language: str | None = Field(default=None, pattern=r"^(en|ta)$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    timezone: str | None = Field(default=None, max_length=64)
    fy_start_month: int | None = Field(default=None, ge=1, le=12)


class PriestAssignmentOut(BaseModel):
    id: str
    role: str
    appointed_on: date
    relieved_on: date | None
    current: bool
    responsibilities: str | None
    appointment_ref: str | None
    relieving_reason: str | None
    remarks: str | None
    grants_role: bool


class PriestOut(BaseModel):
    id: str
    title: str
    full_name: str
    display_name: str
    name_local: str | None
    date_of_birth: date | None
    ordination_date: date | None
    clergy_type: str
    home_diocese: str | None
    congregation: str | None
    phone: str | None
    email: str | None
    status: str
    user: dict[str, str] | None
    remarks: str | None
    current_roles: list[str]
    assignments: list[PriestAssignmentOut]
    created_at: datetime


class PriestIn(BaseModel):
    title: str = Field(default="Rev. Fr.", max_length=50)
    full_name: str = Field(min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None
    ordination_date: date | None = None
    clergy_type: str = Field(default="DIOCESAN", pattern=r"^(DIOCESAN|RELIGIOUS)$")
    home_diocese: str | None = Field(default=None, max_length=200)
    congregation: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    remarks: str | None = Field(default=None, max_length=2000)


class PriestUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=50)
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None
    ordination_date: date | None = None
    clergy_type: str | None = Field(default=None, pattern=r"^(DIOCESAN|RELIGIOUS)$")
    home_diocese: str | None = Field(default=None, max_length=200)
    congregation: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    remarks: str | None = Field(default=None, max_length=2000)


class PriestStatusIn(BaseModel):
    status: str = Field(pattern=r"^(ACTIVE|RETIRED|DECEASED|LEFT)$")


class LinkUserIn(BaseModel):
    user_id: str | None = Field(default=None, description="User public id; null unlinks")


class AppointIn(BaseModel):
    role: str = Field(pattern=r"^(PARISH_PRIEST|ASSISTANT_PRIEST|RESIDENT_PRIEST|DEACON|OTHER)$")
    appointed_on: date
    relieved_on: date | None = None
    responsibilities: str | None = Field(default=None, max_length=2000)
    appointment_ref: str | None = Field(default=None, max_length=100, description="Appointment letter no.")
    remarks: str | None = Field(default=None, max_length=255)
    relieve_current: bool = Field(
        default=False, description="Relieve the current Parish Priest the day before"
    )


class RelieveIn(BaseModel):
    relieved_on: date | None = Field(
        default=None, description="Handover date (first day no longer serving); default today"
    )
    reason: str | None = Field(default=None, max_length=255)


class ClergyOut(BaseModel):
    """Who serves the parish today – visible to every signed-in user."""

    parish_priest: dict[str, str] | None
    others: list[dict[str, str]]

"""Pydantic schemas for platform (master DB) APIs."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class PlatformLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PlatformUserOut(_Out):
    id: str = Field(validation_alias="public_id")
    email: str
    full_name: str
    is_super_admin: bool
    is_active: bool


# ---------------------------------------------------------------- dioceses
class _AddressIn(BaseModel):
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default="India", max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None


class DioceseCreate(_AddressIn):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    name: str = Field(min_length=2, max_length=200)
    bishop_name: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=255)


class DioceseUpdate(_AddressIn):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    bishop_name: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|INACTIVE)$")


class DioceseOut(_Out):
    id: str = Field(validation_alias="public_id")
    code: str
    name: str
    bishop_name: str | None
    city: str | None
    state: str | None
    country: str | None
    phone: str | None
    email: str | None
    website: str | None
    status: str
    created_at: datetime


# ---------------------------------------------------------------- parishes
class ParishCreate(_AddressIn):
    diocese_code: str = Field(min_length=2, max_length=20)
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    name: str = Field(min_length=2, max_length=200)
    subdomain: str | None = Field(default=None, max_length=63)
    established_on: date | None = None
    language: str = Field(default="en", pattern=r"^(en|ta)$")
    currency: str = Field(default="INR", min_length=3, max_length=3)
    fy_start_month: int = Field(default=4, ge=1, le=12)
    # Initial parish administrator; an invitation ("set your password") email is sent.
    admin_username: str | None = Field(
        default=None, min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$"
    )
    admin_full_name: str | None = Field(default=None, max_length=200)
    admin_email: EmailStr | None = None


class ParishStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(ACTIVE|TRIAL|SUSPENDED|ARCHIVED)$")
    remarks: str | None = Field(default=None, max_length=500)


class ParishOut(_Out):
    id: str
    code: str
    subdomain: str
    name: str
    status: str
    diocese_code: str
    diocese_name: str
    city: str | None
    established_on: date | None
    schema_version: str | None
    last_error: str | None
    created_at: datetime
    admin_username: str | None = None


class TenantBrandingOut(BaseModel):
    parish_id: str
    code: str
    name: str
    display_name: str
    logo_url: str | None
    primary_color: str | None
    default_language: str
    currency: str
    diocese_name: str

"""Organisation API schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

CODE = r"^[A-Za-z][A-Za-z0-9_]*$"


class MembershipRules(BaseModel):
    min_age: int | None = Field(default=None, ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)
    genders: list[str] | None = Field(default=None, description="Allowed genders, e.g. ['F']")
    max_units_per_member: int | None = Field(default=None, ge=1, description="Units of this type per member")


class PositionOut(BaseModel):
    id: str
    code: str
    name: str
    name_local: str | None
    role_code: str | None
    role_name: str | None
    max_holders: int | None
    sort_order: int


class PositionIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=CODE)
    name: str = Field(min_length=2, max_length=100)
    name_local: str | None = Field(default=None, max_length=100)
    role_code: str | None = Field(default=None, max_length=50)
    max_holders: int | None = Field(default=1, ge=1)
    sort_order: int = 100


class PositionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    name_local: str | None = Field(default=None, max_length=100)
    role_code: str | None = Field(default=None, max_length=50)
    max_holders: int | None = Field(default=None, ge=1)
    sort_order: int | None = None


class TypeOut(BaseModel):
    id: str
    code: str
    name: str
    name_plural: str
    name_local: str | None
    description: str | None
    member_kind: str
    membership_rules: dict[str, Any]
    allow_multiple_units: bool
    code_prefix: str
    is_system: bool
    sort_order: int
    unit_count: int
    positions: list[PositionOut]


class TypeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=CODE)
    name: str = Field(min_length=2, max_length=100)
    name_plural: str = Field(min_length=2, max_length=100)
    name_local: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    member_kind: str = Field(default="MEMBER", pattern=r"^(MEMBER|FAMILY)$")
    membership_rules: MembershipRules = Field(default_factory=MembershipRules)
    allow_multiple_units: bool = True
    code_prefix: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9]+$")
    sort_order: int = 100
    positions: list[PositionIn] = Field(default_factory=list)


class TypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    name_plural: str | None = Field(default=None, min_length=2, max_length=100)
    name_local: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    membership_rules: MembershipRules | None = None
    allow_multiple_units: bool | None = None
    sort_order: int | None = None


class BearerOut(BaseModel):
    id: str
    position_code: str
    position_name: str
    user_id: str | None
    holder_name: str
    valid_from: date
    valid_to: date | None
    current: bool
    ended_at: datetime | None
    grants_role: str | None
    remarks: str | None


class BearerCreate(BaseModel):
    position_code: str = Field(min_length=2, max_length=30)
    user_id: str | None = Field(default=None, description="User public id (grants the position's role)")
    holder_name: str | None = Field(default=None, max_length=200, description="For people without a login")
    valid_from: date | None = None
    valid_to: date | None = None
    remarks: str | None = Field(default=None, max_length=255)


class BearerEnd(BaseModel):
    end_date: date | None = None


class UnitBrief(BaseModel):
    id: str
    code: str
    name: str


class UnitOut(BaseModel):
    id: str
    code: str
    name: str
    name_local: str | None
    type_code: str
    type_name: str
    parent: UnitBrief | None
    description: str | None
    status: str
    established_on: date | None
    meeting_place: str | None
    meeting_schedule: str | None
    contact_phone: str | None
    contact_email: str | None
    sub_unit_count: int
    office_bearers: list[BearerOut]
    can_manage: bool
    created_at: datetime


class UnitCreate(BaseModel):
    type_code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=200)
    code: str | None = Field(default=None, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    name_local: str | None = Field(default=None, max_length=200)
    parent_id: str | None = None
    description: str | None = Field(default=None, max_length=5000)
    established_on: date | None = None
    meeting_place: str | None = Field(default=None, max_length=255)
    meeting_schedule: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=30)
    contact_email: EmailStr | None = None

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class UnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    parent_id: str | None = Field(default=None, description="Empty string removes the parent")
    description: str | None = Field(default=None, max_length=5000)
    established_on: date | None = None
    meeting_place: str | None = Field(default=None, max_length=255)
    meeting_schedule: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=30)
    contact_email: EmailStr | None = None

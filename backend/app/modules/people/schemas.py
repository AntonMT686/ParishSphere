"""Family & member API schemas.

``MemberOut`` always contains identity fields; *sensitive* fields (date of birth, contacts, education,
occupation, marital status, remarks) are filled only for ``member.view_sensitive`` holders and
*sacramental* fields only for ``sacrament.view`` holders. Age is shown to everyone who may view members.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

Gender = Literal["M", "F", "O"]
Relationship = Literal[
    "HEAD",
    "SPOUSE",
    "SON",
    "DAUGHTER",
    "FATHER",
    "MOTHER",
    "BROTHER",
    "SISTER",
    "GRANDSON",
    "GRANDDAUGHTER",
    "SON_IN_LAW",
    "DAUGHTER_IN_LAW",
    "FATHER_IN_LAW",
    "MOTHER_IN_LAW",
    "GRANDFATHER",
    "GRANDMOTHER",
    "NEPHEW",
    "NIECE",
    "OTHER_RELATIVE",
    "OTHER",
]
Marital = Literal["SINGLE", "MARRIED", "WIDOWED", "SEPARATED", "RELIGIOUS"]

SENSITIVE_FIELDS = ("date_of_birth", "phone", "email", "education", "occupation", "marital_status", "remarks")
SACRAMENT_FIELDS = (
    "baptism_date",
    "baptism_place",
    "baptism_register_ref",
    "communion_date",
    "communion_place",
    "confirmation_date",
    "confirmation_place",
    "marriage_date",
    "marriage_place",
    "marriage_register_ref",
)


class Ref(BaseModel):
    id: str
    code: str
    name: str


# ----------------------------------------------------------------------------- members
class MemberIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    name_local: str | None = Field(default=None, max_length=200)
    gender: Gender
    date_of_birth: date | None = None
    relationship_to_head: Relationship = "OTHER"
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    education: str | None = Field(default=None, max_length=200)
    occupation: str | None = Field(default=None, max_length=200)
    marital_status: Marital | None = None
    baptism_date: date | None = None
    baptism_place: str | None = Field(default=None, max_length=200)
    baptism_register_ref: str | None = Field(default=None, max_length=50)
    communion_date: date | None = None
    communion_place: str | None = Field(default=None, max_length=200)
    confirmation_date: date | None = None
    confirmation_place: str | None = Field(default=None, max_length=200)
    marriage_date: date | None = None
    marriage_place: str | None = Field(default=None, max_length=200)
    marriage_register_ref: str | None = Field(default=None, max_length=50)
    remarks: str | None = Field(default=None, max_length=2000)


class MemberUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    name_local: str | None = Field(default=None, max_length=200)
    gender: Gender | None = None
    date_of_birth: date | None = None
    relationship_to_head: Relationship | None = None
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    education: str | None = Field(default=None, max_length=200)
    occupation: str | None = Field(default=None, max_length=200)
    marital_status: Marital | None = None
    baptism_date: date | None = None
    baptism_place: str | None = Field(default=None, max_length=200)
    baptism_register_ref: str | None = Field(default=None, max_length=50)
    communion_date: date | None = None
    communion_place: str | None = Field(default=None, max_length=200)
    confirmation_date: date | None = None
    confirmation_place: str | None = Field(default=None, max_length=200)
    marriage_date: date | None = None
    marriage_place: str | None = Field(default=None, max_length=200)
    marriage_register_ref: str | None = Field(default=None, max_length=50)
    remarks: str | None = Field(default=None, max_length=2000)


class MemberOut(BaseModel):
    id: str
    code: str
    family: Ref
    anbiyam: Ref | None
    first_name: str
    last_name: str | None
    full_name: str
    name_local: str | None
    gender: str
    age: int | None
    relationship_to_head: str
    is_head: bool
    status: str
    date_of_death: date | None
    sensitive_visible: bool
    sacraments_visible: bool
    # sensitive
    date_of_birth: date | None = None
    phone: str | None = None
    email: str | None = None
    education: str | None = None
    occupation: str | None = None
    marital_status: str | None = None
    remarks: str | None = None
    # sacraments
    baptism_date: date | None = None
    baptism_place: str | None = None
    baptism_register_ref: str | None = None
    communion_date: date | None = None
    communion_place: str | None = None
    confirmation_date: date | None = None
    confirmation_place: str | None = None
    marriage_date: date | None = None
    marriage_place: str | None = None
    marriage_register_ref: str | None = None
    created_at: datetime


class DeceasedIn(BaseModel):
    date_of_death: date
    remarks: str | None = Field(default=None, max_length=500)


class MoveMemberIn(BaseModel):
    family_id: str
    relationship_to_head: Relationship = "OTHER"
    new_head_member_id: str | None = Field(default=None, description="Required when the head leaves a family")
    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=255)


class StatusIn(BaseModel):
    active: bool
    reason: str | None = Field(default=None, max_length=255)


# ----------------------------------------------------------------------------- families
class FamilyBase(BaseModel):
    family_name: str = Field(min_length=1, max_length=200)
    family_name_local: str | None = Field(default=None, max_length=200)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    previous_parish: str | None = Field(default=None, max_length=200)
    previous_diocese: str | None = Field(default=None, max_length=200)
    remarks: str | None = Field(default=None, max_length=2000)


class FamilyCreate(FamilyBase):
    anbiyam_id: str | None = Field(default=None, description="Anbiyam (org unit) public id; empty = pending")
    registered_on: date | None = None
    members: list[MemberIn] = Field(min_length=1, max_length=40)
    confirm_not_duplicate: bool = Field(
        default=False, description="Register even though similar families exist (after reviewing them)"
    )


class FamilyUpdate(BaseModel):
    family_name: str | None = Field(default=None, min_length=1, max_length=200)
    family_name_local: str | None = Field(default=None, max_length=200)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    previous_parish: str | None = Field(default=None, max_length=200)
    previous_diocese: str | None = Field(default=None, max_length=200)
    remarks: str | None = Field(default=None, max_length=2000)


class DuplicateCheckIn(BaseModel):
    family_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    members: list[MemberIn] = Field(default_factory=list, max_length=40)


class DuplicateOut(BaseModel):
    family_id: str
    family_code: str
    family_name: str
    status: str
    reasons: list[str]


class FamilyListOut(BaseModel):
    id: str
    code: str
    family_name: str
    family_name_local: str | None
    head_name: str | None
    anbiyam: Ref | None
    member_count: int
    phone: str | None
    city: str | None
    status: str
    registered_on: date


class FamilyOut(FamilyListOut):
    address_line1: str | None
    address_line2: str | None
    state: str | None
    postal_code: str | None
    email: str | None
    previous_parish: str | None
    previous_diocese: str | None
    remarks: str | None
    merged_into: Ref | None
    head_member_id: str | None
    members: list[MemberOut]
    created_at: datetime


class ChangeAnbiyamIn(BaseModel):
    anbiyam_id: str | None = Field(default=None, description="Empty removes the family from its Anbiyam")
    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=255)


class SetHeadIn(BaseModel):
    member_id: str
    previous_head_relationship: Relationship = "OTHER"


class TransferOutIn(BaseModel):
    to_parish: str = Field(min_length=2, max_length=200)
    to_diocese: str | None = Field(default=None, max_length=200)
    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=255)


class MergeIn(BaseModel):
    into_family_id: str
    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=255)


class SplitIn(BaseModel):
    member_ids: list[str] = Field(min_length=1)
    head_member_id: str
    remaining_head_member_id: str | None = None
    new_family: FamilyUpdate = Field(default_factory=FamilyUpdate)
    anbiyam_id: str | None = Field(default=None, description="Defaults to the current Anbiyam")
    effective_date: date | None = None
    reason: str | None = Field(default=None, max_length=255)


class FamilyEventOut(BaseModel):
    event_type: str
    occurred_on: date
    created_at: datetime
    member: Ref | None
    related_family: Ref | None
    details: dict[str, Any]
    performed_by: str | None


class AnbiyamHistoryOut(BaseModel):
    anbiyam: Ref
    valid_from: date
    valid_to: date | None
    reason: str | None


class FamilyHistoryOut(BaseModel):
    events: list[FamilyEventOut]
    anbiyam_history: list[AnbiyamHistoryOut]


# ----------------------------------------------------------------------------- memberships
class MembershipIn(BaseModel):
    member_id: str | None = None
    family_id: str | None = None
    joined_on: date | None = None
    remarks: str | None = Field(default=None, max_length=255)


class MembershipEndIn(BaseModel):
    left_on: date | None = None
    reason: str | None = Field(default=None, max_length=100)


class MembershipOut(BaseModel):
    id: str | None  # None for Anbiyam families (membership is the family's Anbiyam)
    org_unit: Ref
    member: Ref | None
    family: Ref | None
    gender: str | None = None
    age: int | None = None
    joined_on: date | None
    left_on: date | None
    current: bool
    remarks: str | None = None

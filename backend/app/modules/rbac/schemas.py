"""Role & permission API schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class PermissionOut(BaseModel):
    code: str
    module: str
    action: str
    description: str | None


class PermissionModuleOut(BaseModel):
    module: str
    permissions: list[PermissionOut]


class RoleSummaryOut(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    is_system: bool
    scope_type: str
    permission_count: int
    active_users: int


class RoleOut(RoleSummaryOut):
    permissions: list[str]


class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    scope_type: str = Field(default="PARISH", pattern=r"^(PARISH|ORG_UNIT|ANY)$")
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    permissions: list[str] | None = None


class AssignmentCreate(BaseModel):
    role_code: str = Field(min_length=2, max_length=50)
    org_unit_id: str | None = Field(
        default=None, description="Organisation unit public id (org-scoped roles)"
    )
    valid_from: date | None = None
    valid_to: date | None = None
    remarks: str | None = Field(default=None, max_length=255)


class AssignmentOut(BaseModel):
    id: str
    role_code: str
    role_name: str
    org_unit_id: str | None
    valid_from: date
    valid_to: date | None
    active: bool
    created_at: datetime
    ended_at: datetime | None
    remarks: str | None

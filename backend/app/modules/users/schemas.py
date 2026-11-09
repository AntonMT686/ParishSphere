"""User administration schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    preferred_language: str = Field(default="en", pattern=r"^(en|ta)$")
    password: str | None = Field(
        default=None, max_length=256, description="Set an initial password. Omit to email an invitation link."
    )
    role_codes: list[str] = Field(default_factory=list, description="Parish-wide roles to assign immediately")

    @model_validator(mode="after")
    def _password_or_email(self) -> UserCreate:
        if not self.password and not self.email:
            raise ValueError("Provide either a password or an email address for the invitation")
        return self


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    preferred_language: str | None = Field(default=None, pattern=r"^(en|ta)$")


class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    email: str | None
    phone: str | None
    preferred_language: str
    is_active: bool
    is_locked: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    roles: list[str]

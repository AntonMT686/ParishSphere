"""Auth API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=255, description="Username or email")
    password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(validation_alias="public_id")
    username: str
    full_name: str
    email: str | None
    phone: str | None
    preferred_language: str
    must_change_password: bool
    last_login_at: datetime | None
    # Filled by RBAC (T4).
    roles: list[str] = []
    permissions: list[str] = []


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    idle_timeout_seconds: int
    user: MeOut


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class ForgotPasswordIn(BaseModel):
    username: str = Field(min_length=1, max_length=255, description="Username or email")


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    id: str
    issued_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool


class MessageOut(BaseModel):
    message: str

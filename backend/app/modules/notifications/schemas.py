"""Notification API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: str
    event_code: str
    title: str
    body: str
    link: str | None
    entity_type: str | None
    entity_id: str | None
    is_important: bool
    is_read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread: int


class PreferenceOut(BaseModel):
    event_code: str
    description: str
    channel: str
    enabled: bool
    default: bool


class PreferenceIn(BaseModel):
    event_code: str = Field(max_length=60)
    channel: str = Field(pattern=r"^(IN_APP|EMAIL)$")
    enabled: bool


class TemplateOut(BaseModel):
    event_code: str
    description: str
    variables: list[str]
    channel: str
    language: str
    subject: str
    body: str
    is_override: bool


class TemplateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=5000)


class BroadcastIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=2000)
    role_codes: list[str] = Field(default_factory=list, description="Empty = all active users")
    link: str | None = Field(default=None, max_length=500, pattern=r"^/[^\s]*$")

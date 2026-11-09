"""Parish user accounts, login sessions, refresh tokens and password-reset tokens."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntPK, IdMixin, PublicIdMixin, StandardMixin, TenantBase, utcnow


class User(StandardMixin, TenantBase):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Link to the parish member record (FK added when the members table exists – T8).
    member_id: Mapped[int | None] = mapped_column(BigIntPK, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime())
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime())
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime())

    sessions: Mapped[list[UserSession]] = relationship(back_populates="user")


class UserSession(IdMixin, PublicIdMixin, TenantBase):
    """A login session. ``public_id`` is the ``sid`` claim of access tokens."""

    __tablename__ = "user_sessions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(), index=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(30))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="sessions")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="session")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


class RefreshToken(IdMixin, TenantBase):
    """Opaque refresh tokens (stored hashed). Each is single-use; reuse revokes the session."""

    __tablename__ = "refresh_tokens"

    session_id: Mapped[int] = mapped_column(ForeignKey("user_sessions.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime())

    session: Mapped[UserSession] = relationship(back_populates="refresh_tokens")


class PasswordResetToken(IdMixin, TenantBase):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime())
    requested_ip: Mapped[str | None] = mapped_column(String(45))

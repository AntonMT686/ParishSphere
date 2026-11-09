"""Declarative bases and reusable column mixins.

Two independent metadata objects exist:

* ``MasterBase`` – tables in the central master database.
* ``TenantBase`` – tables replicated in every parish database.

They must never be mixed: a model belongs to exactly one of them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_public_id

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# BIGINT on MySQL, INTEGER on SQLite (required for SQLite rowid autoincrement in tests/dev).
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class MasterBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)


class PublicIdMixin:
    public_id: Mapped[str] = mapped_column(String(26), unique=True, nullable=False, default=new_public_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class ActorMixin:
    created_by: Mapped[int | None] = mapped_column(BigIntPK, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigIntPK, nullable=True)


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(BigIntPK, nullable=True)

    def soft_delete(self, actor_id: int | None = None) -> None:
        self.is_deleted = True
        self.deleted_at = utcnow()
        self.deleted_by = actor_id


class StandardMixin(IdMixin, PublicIdMixin, TimestampMixin, ActorMixin, SoftDeleteMixin):
    """Default column set for business tables: id, public_id, audit stamps, soft delete."""

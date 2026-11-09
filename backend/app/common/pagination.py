"""Pagination & sorting helpers shared by all list endpoints."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed

T = TypeVar("T")
MAX_PAGE_SIZE = 100


class PageParams(BaseModel):
    page: int = 1
    size: int = 25
    sort: str | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
    sort: Annotated[str | None, Query(max_length=200, description="e.g. `name,-created_at`")] = None,
) -> PageParams:
    return PageParams(page=page, size=size, sort=sort)


PageQuery = Annotated[PageParams, Depends(page_params)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int
    pages: int


def apply_sort(
    stmt: Select[Any], sort: str | None, allowed: dict[str, Any], default: Sequence[Any]
) -> Select[Any]:
    """Apply a ``sort=field,-other`` expression restricted to an allow-list of columns."""
    if not sort:
        return stmt.order_by(*default)
    clauses = []
    for raw in sort.split(","):
        raw = raw.strip()
        if not raw:
            continue
        desc = raw.startswith("-")
        key = raw.lstrip("-+")
        if key not in allowed:
            raise ValidationFailed(details=[{"field": "sort", "message": f"Cannot sort by '{key}'"}])
        col = allowed[key]
        clauses.append(col.desc() if desc else col.asc())
    return stmt.order_by(*clauses, *default)


def paginate(
    session: Session,
    stmt: Select[Any],
    params: PageParams,
    mapper: Callable[[Any], T],
) -> Page[T]:
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.scalars(stmt.limit(params.size).offset(params.offset)).unique().all()
    return Page[T](
        items=[mapper(r) for r in rows],
        page=params.page,
        size=params.size,
        total=total,
        pages=math.ceil(total / params.size) if total else 0,
    )

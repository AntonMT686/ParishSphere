"""Business code generator (FAM000123, TXN-2026-000045 …).

Rows in ``sequences`` are locked with ``SELECT … FOR UPDATE`` so concurrent requests never receive the
same code. Yearly sequences keep one counter row per year (``TRANSACTION:2026``), created on demand
from the base row (which is locked first, serialising creation).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.core.models import Sequence


class UnknownSequence(LookupError):
    pass


def _locked(session: Session, name: str) -> Sequence | None:
    return session.scalars(select(Sequence).where(Sequence.name == name).with_for_update()).first()


def format_code(fmt: str, prefix: str, number: int, padding: int, year: int) -> str:
    return fmt.format(prefix=prefix, year=year, number=str(number).zfill(padding))


def next_code(session: Session, name: str, on: date | None = None) -> str:
    """Return the next code for sequence ``name`` (e.g. ``"FAMILY"``) and advance the counter."""
    base = _locked(session, name)
    if base is None:
        raise UnknownSequence(name)
    year = (on or date.today()).year
    row = base
    if base.yearly:
        key = f"{name}:{year}"
        row = _locked(session, key) or Sequence(
            name=key, prefix=base.prefix, padding=base.padding, format=base.format, yearly=False, next_value=1
        )
        if row not in session:
            session.add(row)
    value = row.next_value
    row.next_value = value + 1
    session.flush()
    return format_code(base.format, base.prefix, value, base.padding, year)


def peek_code(session: Session, name: str, on: date | None = None) -> str:
    """The code the next call to :func:`next_code` would return (for form previews; not reserved)."""
    base = session.get(Sequence, name)
    if base is None:
        raise UnknownSequence(name)
    year = (on or date.today()).year
    row = session.get(Sequence, f"{name}:{year}") if base.yearly else base
    return format_code(base.format, base.prefix, row.next_value if row else 1, base.padding, year)

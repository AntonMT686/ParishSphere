"""Default data seeded into every new parish database.

Seeders are idempotent: running them again never duplicates rows. Later modules register
additional seeders with :func:`register_seeder` (roles, org unit types, workflows …).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.modules.core.models import Sequence, Setting

Seeder = Callable[[Session, dict[str, Any]], None]
_SEEDERS: list[tuple[int, str, Seeder]] = []


def register_seeder(name: str, order: int = 100) -> Callable[[Seeder], Seeder]:
    def deco(fn: Seeder) -> Seeder:
        if all(n != name for _, n, _ in _SEEDERS):
            _SEEDERS.append((order, name, fn))
            _SEEDERS.sort(key=lambda t: t[0])
        return fn

    return deco


DEFAULT_SEQUENCES: dict[str, tuple[str, int]] = {
    "FAMILY": ("FAM", 6),
    "MEMBER": ("MEM", 6),
    "ACTIVITY": ("ACT", 6),
    "MEETING": ("MTG", 6),
    "ACTION_ITEM": ("AI", 6),
    "TRANSACTION": ("TXN", 6),
    "NOTICE": ("NTC", 6),
}


@register_seeder("core.settings", order=10)
def seed_settings(session: Session, ctx: dict[str, Any]) -> None:
    defaults: dict[str, Any] = {
        "parish.name": ctx.get("parish_name"),
        "parish.code": ctx.get("parish_code"),
        "finance.fy_start_month": ctx.get("fy_start_month", 4),
        "finance.currency": ctx.get("currency", "INR"),
        "i18n.default_language": ctx.get("language", "en"),
        "i18n.supported_languages": ["en", "ta"],
        "security.idle_timeout_minutes": 30,
        "workflow.allow_self_approval": False,
    }
    for key, value in defaults.items():
        if session.get(Setting, key) is None:
            session.add(Setting(key=key, value=value))


@register_seeder("core.sequences", order=11)
def seed_sequences(session: Session, _: dict[str, Any]) -> None:
    for name, (prefix, padding) in DEFAULT_SEQUENCES.items():
        if session.get(Sequence, name) is None:
            session.add(Sequence(name=name, prefix=prefix, padding=padding, next_value=1))


def run_seeders(session: Session, ctx: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    for _, name, fn in _SEEDERS:
        fn(session, ctx)
        session.flush()
        applied.append(name)
    return applied

"""Programmatic Alembic runners for the master DB and parish DBs."""

from __future__ import annotations

import threading
from typing import Literal

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from app.core.config import BACKEND_DIR

Env = Literal["master", "tenant"]

# Alembic keeps global proxies (``alembic.context``/``op``): never run two upgrades in one process at once.
_ALEMBIC_LOCK = threading.Lock()


def alembic_config(env: Env) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"), ini_section=env)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations" / env))
    return cfg


def head_revision(env: Env) -> str | None:
    return ScriptDirectory.from_config(alembic_config(env)).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def upgrade(engine: Engine, env: Env, revision: str = "head") -> str | None:
    """Upgrade the database behind ``engine`` and return its new revision."""
    cfg = alembic_config(env)
    with _ALEMBIC_LOCK, engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)
    return current_revision(engine)

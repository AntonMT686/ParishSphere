"""Physical database administration used during parish provisioning.

``MySQLAdmin`` creates a dedicated database and (in production) a dedicated MySQL user with
privileges limited to that database. ``SQLiteAdmin`` is used for local development and tests.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.core.config import get_settings

_SAFE_IDENT = re.compile(r"^[a-z0-9_]{1,64}$")


def _ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Unsafe database identifier: {name!r}")
    return name


class DatabaseAdmin(ABC):
    @abstractmethod
    def database_exists(self, db_name: str) -> bool: ...

    @abstractmethod
    def create_database(self, db_name: str) -> None: ...

    @abstractmethod
    def create_user(self, db_name: str, user: str, password: str) -> None: ...

    @abstractmethod
    def drop_database(self, db_name: str) -> None: ...


class MySQLAdmin(DatabaseAdmin):
    def __init__(self, host: str, port: int) -> None:
        s = get_settings()
        self._url = URL.create(
            "mysql+pymysql",
            username=s.tenant_db_admin_user,
            password=s.tenant_db_admin_password.get_secret_value(),
            host=host,
            port=port,
            query={"charset": "utf8mb4"},
        )

    def _exec(self, *statements: str, params: dict[str, str] | None = None) -> None:
        engine = create_engine(self._url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                for stmt in statements:
                    conn.execute(text(stmt), params or {})
        finally:
            engine.dispose()

    def database_exists(self, db_name: str) -> bool:
        engine = create_engine(self._url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :n"),
                    {"n": db_name},
                ).first()
                return row is not None
        finally:
            engine.dispose()

    def create_database(self, db_name: str) -> None:
        self._exec(
            f"CREATE DATABASE IF NOT EXISTS `{_ident(db_name)}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )

    def create_user(self, db_name: str, user: str, password: str) -> None:
        db, usr = _ident(db_name), _ident(user)
        self._exec(
            f"CREATE USER IF NOT EXISTS '{usr}'@'%' IDENTIFIED BY :pw",
            f"ALTER USER '{usr}'@'%' IDENTIFIED BY :pw",
            f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES, "
            f"CREATE TEMPORARY TABLES, LOCK TABLES ON `{db}`.* TO '{usr}'@'%'",
            params={"pw": password},
        )

    def drop_database(self, db_name: str) -> None:
        self._exec(f"DROP DATABASE IF EXISTS `{_ident(db_name)}`")


class SQLiteAdmin(DatabaseAdmin):
    def _path(self, db_name: str):  # type: ignore[no-untyped-def]
        s = get_settings()
        s.sqlite_data_dir.mkdir(parents=True, exist_ok=True)
        return s.sqlite_data_dir / f"{_ident(db_name)}.db"

    def database_exists(self, db_name: str) -> bool:
        return self._path(db_name).exists()

    def create_database(self, db_name: str) -> None:
        self._path(db_name).touch(exist_ok=True)

    def create_user(self, db_name: str, user: str, password: str) -> None:
        """SQLite has no users; isolation is by file."""

    def drop_database(self, db_name: str) -> None:
        self._path(db_name).unlink(missing_ok=True)


def get_db_admin(host: str | None = None, port: int | None = None) -> DatabaseAdmin:
    s = get_settings()
    if s.tenant_db_driver == "sqlite":
        return SQLiteAdmin()
    return MySQLAdmin(host or s.tenant_db_host, port or s.tenant_db_port)

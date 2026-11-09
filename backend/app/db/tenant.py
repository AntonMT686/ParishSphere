"""Per-parish engine registry and tenant session management.

Each parish has its own database. ``EngineRegistry`` lazily creates one pooled engine per
tenant and keeps at most ``tenant_engine_cache_size`` engines alive (LRU). Evicted engines
are disposed, closing their pooled connections.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import decrypt_secret


@dataclass(frozen=True, slots=True)
class TenantDescriptor:
    """Everything needed to route a request to a parish database (cached, immutable)."""

    parish_id: int
    public_id: str
    code: str
    subdomain: str
    name: str
    status: str
    diocese_public_id: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str | None
    db_password_enc: bytes | None

    @property
    def is_operational(self) -> bool:
        return self.status in ("ACTIVE", "TRIAL")


def build_tenant_url(tenant: TenantDescriptor) -> URL:
    settings = get_settings()
    if settings.tenant_db_driver == "sqlite":
        settings.sqlite_data_dir.mkdir(parents=True, exist_ok=True)
        return make_url(f"sqlite:///{settings.sqlite_data_dir / (tenant.db_name + '.db')}")
    if settings.tenant_db_shared_credentials or not tenant.db_user or not tenant.db_password_enc:
        user, password = settings.tenant_db_admin_user, settings.tenant_db_admin_password.get_secret_value()
    else:
        user, password = tenant.db_user, decrypt_secret(tenant.db_password_enc)
    return URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=tenant.db_host,
        port=tenant.db_port,
        database=tenant.db_name,
        query={"charset": "utf8mb4"},
    )


def create_tenant_engine(url: URL) -> Engine:
    settings = get_settings()
    if url.get_backend_name() == "sqlite":
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # type: ignore[no-untyped-def]
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(
        url,
        pool_size=settings.tenant_pool_size,
        max_overflow=settings.tenant_max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.tenant_pool_recycle_seconds,
    )


class EngineRegistry:
    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._engines: OrderedDict[str, tuple[Engine, sessionmaker[Session]]] = OrderedDict()
        self._lock = threading.Lock()

    def _entry(self, tenant: TenantDescriptor) -> tuple[Engine, sessionmaker[Session]]:
        with self._lock:
            entry = self._engines.get(tenant.code)
            if entry is not None:
                self._engines.move_to_end(tenant.code)
                return entry
            engine = create_tenant_engine(build_tenant_url(tenant))
            entry = (engine, sessionmaker(bind=engine, expire_on_commit=False))
            self._engines[tenant.code] = entry
            while len(self._engines) > self._max_size:
                _, (old_engine, _) = self._engines.popitem(last=False)
                old_engine.dispose()
            return entry

    def engine(self, tenant: TenantDescriptor) -> Engine:
        return self._entry(tenant)[0]

    def session(self, tenant: TenantDescriptor) -> Session:
        return self._entry(tenant)[1]()

    def evict(self, code: str) -> None:
        with self._lock:
            entry = self._engines.pop(code, None)
        if entry is not None:
            entry[0].dispose()

    def dispose_all(self) -> None:
        with self._lock:
            entries = list(self._engines.values())
            self._engines.clear()
        for engine, _ in entries:
            engine.dispose()

    def __len__(self) -> int:
        return len(self._engines)

    def __contains__(self, code: object) -> bool:
        return code in self._engines


_registry: EngineRegistry | None = None
_registry_lock = threading.Lock()


def get_engine_registry() -> EngineRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = EngineRegistry(get_settings().tenant_engine_cache_size)
    return _registry


def reset_engine_registry() -> None:
    global _registry
    if _registry is not None:
        _registry.dispose_all()
    _registry = None


@contextmanager
def tenant_session_scope(tenant: TenantDescriptor) -> Iterator[Session]:
    """Transactional session for a tenant outside a request (CLI, Celery)."""
    session = get_engine_registry().session(tenant)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

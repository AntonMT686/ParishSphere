"""Tenant resolution: request host / header → ``TenantDescriptor`` (cached).

Precedence (see docs/03-multi-tenant-architecture.md):

1. Subdomain of ``Host`` under ``PS_BASE_DOMAIN`` (e.g. ``stmarys.parishsphere.app``)
2. ``X-Parish-Code`` header (login page on shared domain / localhost)

The tenant is *never* taken from the request body or query string.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from dataclasses import asdict
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.db.master import master_session
from app.db.tenant import TenantDescriptor
from app.master.models import Parish

log = structlog.get_logger(__name__)

PARISH_CODE_HEADER = "x-parish-code"


def extract_subdomain(host: str | None) -> str | None:
    """Return the tenant subdomain from a Host header, or None for the bare/reserved domain."""
    if not host:
        return None
    settings = get_settings()
    hostname = host.split(":", 1)[0].strip().lower().rstrip(".")
    base = settings.base_domain.lower().strip(".")
    if not hostname.endswith("." + base):
        return None
    sub = hostname[: -(len(base) + 1)]
    if not sub or "." in sub or sub in settings.reserved_subdomains:
        return None
    return sub


def normalize_code(code: str) -> str:
    return code.strip().upper()


# --------------------------------------------------------------------------- cache
class _TenantCache:
    """Small TTL cache: Redis when configured, otherwise in-process."""

    def __init__(self) -> None:
        self._local: dict[str, tuple[float, TenantDescriptor | None]] = {}
        self._lock = threading.Lock()
        self._redis: Any = None
        settings = get_settings()
        if settings.redis_url:
            try:
                import redis

                self._redis = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5)
            except Exception:  # pragma: no cover - redis optional
                log.warning("tenant_cache_redis_unavailable")

    @staticmethod
    def _encode(t: TenantDescriptor) -> str:
        data = asdict(t)
        if data["db_password_enc"] is not None:
            data["db_password_enc"] = base64.b64encode(data["db_password_enc"]).decode()
        return json.dumps(data)

    @staticmethod
    def _decode(raw: str | bytes) -> TenantDescriptor:
        data = json.loads(raw)
        if data["db_password_enc"] is not None:
            data["db_password_enc"] = base64.b64decode(data["db_password_enc"])
        return TenantDescriptor(**data)

    def get(self, key: str) -> TenantDescriptor | None:
        now = time.monotonic()
        with self._lock:
            hit = self._local.get(key)
            if hit and hit[0] > now:
                return hit[1]
        if self._redis is not None:
            try:
                raw = self._redis.get(f"ps:tenant:{key}")
                if raw:
                    t = self._decode(raw)
                    self._set_local(key, t)
                    return t
            except Exception:  # pragma: no cover
                log.warning("tenant_cache_redis_get_failed")
        return None

    def _set_local(self, key: str, value: TenantDescriptor) -> None:
        ttl = get_settings().tenant_cache_ttl_seconds
        with self._lock:
            self._local[key] = (time.monotonic() + min(ttl, 60), value)

    def set(self, key: str, value: TenantDescriptor) -> None:
        self._set_local(key, value)
        if self._redis is not None:
            try:
                self._redis.setex(
                    f"ps:tenant:{key}", get_settings().tenant_cache_ttl_seconds, self._encode(value)
                )
            except Exception:  # pragma: no cover
                log.warning("tenant_cache_redis_set_failed")

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._local.pop(k, None)
        if self._redis is not None and keys:
            try:
                self._redis.delete(*[f"ps:tenant:{k}" for k in keys])
            except Exception:  # pragma: no cover
                log.warning("tenant_cache_redis_delete_failed")

    def clear(self) -> None:
        with self._lock:
            self._local.clear()


_cache: _TenantCache | None = None


def tenant_cache() -> _TenantCache:
    global _cache
    if _cache is None:
        _cache = _TenantCache()
    return _cache


def reset_tenant_cache() -> None:
    global _cache
    _cache = None


# --------------------------------------------------------------------------- lookup
def descriptor_from_parish(parish: Parish) -> TenantDescriptor:
    db = parish.database
    if db is None:
        raise ValueError(f"Parish {parish.code} has no tenant database mapping")
    return TenantDescriptor(
        parish_id=parish.id,
        public_id=parish.public_id,
        code=parish.code,
        subdomain=parish.subdomain,
        name=parish.name,
        status=parish.status,
        diocese_public_id=parish.diocese.public_id,
        db_host=db.db_host,
        db_port=db.db_port,
        db_name=db.db_name,
        db_user=db.db_user,
        db_password_enc=db.db_password_enc,
    )


def load_tenant(
    session: Session, *, code: str | None = None, subdomain: str | None = None
) -> TenantDescriptor | None:
    stmt = (
        select(Parish)
        .options(joinedload(Parish.database), joinedload(Parish.diocese))
        .where(Parish.is_deleted.is_(False))
    )
    if code is not None:
        stmt = stmt.where(Parish.code == normalize_code(code))
    elif subdomain is not None:
        stmt = stmt.where(Parish.subdomain == subdomain.lower())
    else:
        return None
    parish = session.scalars(stmt).first()
    if parish is None or parish.database is None:
        return None
    return descriptor_from_parish(parish)


def resolve_tenant(*, code: str | None = None, subdomain: str | None = None) -> TenantDescriptor | None:
    key = f"sub:{subdomain.lower()}" if subdomain else f"code:{normalize_code(code)}" if code else None
    if key is None:
        return None
    cache = tenant_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached
    with master_session() as session:
        tenant = load_tenant(session, code=code, subdomain=subdomain)
    if tenant is not None:
        cache.set(key, tenant)
    return tenant


def invalidate_tenant(tenant_code: str, subdomain: str | None = None) -> None:
    keys = [f"code:{normalize_code(tenant_code)}"]
    if subdomain:
        keys.append(f"sub:{subdomain.lower()}")
    tenant_cache().invalidate(*keys)

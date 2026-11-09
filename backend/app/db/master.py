"""Master database engine and session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _engine_kwargs(url: str, pool_size: int) -> dict[str, object]:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_size": pool_size, "max_overflow": pool_size, "pool_pre_ping": True, "pool_recycle": 1800}


@lru_cache
def get_master_engine() -> Engine:
    settings = get_settings()
    url = settings.master_database_url
    return create_engine(url, **_engine_kwargs(url, settings.master_pool_size))  # type: ignore[arg-type]


@lru_cache
def _master_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_master_engine(), expire_on_commit=False)


def master_session() -> Session:
    return _master_sessionmaker()()


def get_master_session() -> Iterator[Session]:
    """FastAPI dependency: master DB session with commit/rollback."""
    session = master_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_master_engine() -> None:
    """Dispose cached engine (used by tests after changing settings)."""
    if get_master_engine.cache_info().currsize:
        get_master_engine().dispose()
    get_master_engine.cache_clear()
    _master_sessionmaker.cache_clear()

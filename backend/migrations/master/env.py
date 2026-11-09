"""Alembic environment for the central master database."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.registry import master_metadata

config = context.config


def run_migrations() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(
            connection=connection, target_metadata=master_metadata, render_as_batch=True, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    url = context.get_x_argument(as_dictionary=True).get("url") or get_settings().master_database_url
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=master_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(
            connection=conn, target_metadata=master_metadata, render_as_batch=True, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()

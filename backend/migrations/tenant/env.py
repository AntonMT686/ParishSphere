"""Alembic environment for parish (tenant) databases.

Targets, in order of precedence:
  * ``config.attributes["connection"]`` – used by provisioning / ``ps-admin migrate-tenants``
  * ``-x url=<sqlalchemy url>``
  * ``-x tenant=<PARISH_CODE>`` – resolved through the master database
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from app.db.registry import tenant_metadata

config = context.config


def _url_from_args() -> str:
    args = context.get_x_argument(as_dictionary=True)
    if "url" in args:
        return args["url"]
    if "tenant" in args:
        from app.db.tenant import build_tenant_url
        from app.tenancy.resolver import resolve_tenant

        tenant = resolve_tenant(code=args["tenant"])
        if tenant is None:
            raise SystemExit(f"Unknown tenant {args['tenant']!r}")
        return build_tenant_url(tenant).render_as_string(hide_password=False)
    raise SystemExit("Provide -x tenant=<CODE> or -x url=<URL>; prefer `ps-admin migrate-tenants`.")


def _configure(**kwargs: object) -> None:
    context.configure(target_metadata=tenant_metadata, render_as_batch=True, compare_type=True, **kwargs)


def run_migrations() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = _url_from_args()
    if context.is_offline_mode():
        _configure(url=url, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(url)
    with engine.connect() as conn:
        _configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()

"""``ps-admin`` – operational CLI for ParishSphere.

Examples::

    ps-admin migrate-master
    ps-admin create-superadmin --email admin@example.org --name "Platform Admin"
    ps-admin create-diocese --code CHN --name "Archdiocese of Madras-Mylapore"
    ps-admin provision-parish --diocese CHN --code STMARYS --name "St. Mary's Church"
    ps-admin migrate-tenants --parallel 8
"""

from __future__ import annotations

import getpass
from typing import Annotated

import typer
from sqlalchemy import select

from app.core.logging import configure_logging
from app.db import migrations
from app.db.master import get_master_engine, master_session
from app.master.auth import create_platform_user
from app.master.models import Diocese, PlatformUser
from app.tenancy.provisioning import (
    ParishRegistration,
    migrate_all_tenants,
    provision_parish,
    register_parish,
)

app = typer.Typer(help="ParishSphere administration CLI", no_args_is_help=True)


@app.callback()
def _main() -> None:
    configure_logging("WARNING")


@app.command("migrate-master")
def migrate_master(revision: str = "head") -> None:
    """Upgrade the master database schema."""
    rev = migrations.upgrade(get_master_engine(), "master", revision)
    typer.echo(f"master database at revision {rev}")


@app.command("migrate-tenants")
def migrate_tenants(
    only: Annotated[list[str] | None, typer.Option("--only", help="Parish code(s) to migrate")] = None,
    parallel: Annotated[int, typer.Option(min=1, max=32)] = 4,
) -> None:
    """Upgrade every parish database to the latest tenant schema."""
    results = migrate_all_tenants(only=only, parallel=parallel)
    failed = 0
    for r in results:
        if r.ok:
            typer.echo(f"  OK    {r.code:<20} {r.revision}")
        else:
            failed += 1
            typer.echo(f"  FAIL  {r.code:<20} {r.error}", err=True)
    typer.echo(f"{len(results) - failed}/{len(results)} parish databases migrated")
    if failed:
        raise typer.Exit(code=1)


@app.command("create-superadmin")
def create_superadmin(
    email: Annotated[str, typer.Option(prompt=True)],
    name: Annotated[str, typer.Option(prompt=True)],
    password: Annotated[str | None, typer.Option(help="Omit to be prompted securely")] = None,
) -> None:
    """Create a platform super administrator."""
    pw = password or getpass.getpass("Password: ")
    if len(pw) < 10:
        raise typer.BadParameter("Password must be at least 10 characters")
    with master_session() as session:
        if session.scalars(select(PlatformUser.id).where(PlatformUser.email == email.lower())).first():
            raise typer.BadParameter("User already exists")
        create_platform_user(session, email=email, full_name=name, password=pw, is_super_admin=True)
        session.commit()
    typer.echo(f"super admin {email} created")


@app.command("create-diocese")
def create_diocese(
    code: Annotated[str, typer.Option()],
    name: Annotated[str, typer.Option()],
    bishop: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Register a diocese."""
    with master_session() as session:
        if session.scalars(select(Diocese.id).where(Diocese.code == code.upper())).first():
            raise typer.BadParameter("Diocese code already exists")
        session.add(Diocese(code=code.upper(), name=name, bishop_name=bishop))
        session.commit()
    typer.echo(f"diocese {code.upper()} created")


@app.command("provision-parish")
def provision(
    diocese: Annotated[str, typer.Option(help="Diocese code")],
    code: Annotated[str, typer.Option(help="Parish code, e.g. STMARYS")],
    name: Annotated[str, typer.Option()],
    subdomain: Annotated[str | None, typer.Option()] = None,
    language: Annotated[str, typer.Option()] = "en",
) -> None:
    """Register a parish (if new) and provision its dedicated database. Safe to re-run."""
    with master_session() as session:
        register_parish(
            session,
            ParishRegistration(
                diocese_code=diocese, code=code, name=name, subdomain=subdomain, language=language
            ),
        )
        session.commit()
    tenant = provision_parish(code)
    typer.echo(f"parish {tenant.code} provisioned → database {tenant.db_name} (subdomain {tenant.subdomain})")


if __name__ == "__main__":
    app()

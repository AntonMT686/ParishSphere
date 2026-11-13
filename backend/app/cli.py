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

from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.security import generate_token
from app.db import migrations
from app.db.master import get_master_engine, master_session
from app.db.tenant import tenant_session_scope
from app.master.auth import create_platform_user
from app.master.models import Diocese, PlatformUser
from app.modules.identity.service import create_initial_admin, create_user, send_reset_link
from app.modules.rbac.catalog import ADMIN_ROLE
from app.modules.rbac.service import assign_role, role_by_code
from app.tenancy.provisioning import (
    ParishRegistration,
    migrate_all_tenants,
    provision_parish,
    register_parish,
)
from app.tenancy.resolver import resolve_tenant

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
    admin_username: Annotated[str | None, typer.Option(help="Create the first parish admin")] = None,
    admin_email: Annotated[str | None, typer.Option(help="Admin email (sends a set-password link)")] = None,
    admin_password: Annotated[str | None, typer.Option(help="Set the admin password directly")] = None,
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
    if admin_username:
        _create_admin(tenant.code, admin_username, "Parish Administrator", admin_email, admin_password)


def _create_admin(
    code: str,
    username: str,
    full_name: str,
    email: str | None,
    password: str | None,
    roles: list[str] | None = None,
) -> None:
    """Create a parish user. ``roles=None`` means "initial administrator" (PARISH_ADMIN)."""
    tenant = resolve_tenant(code=code)
    if tenant is None:
        raise typer.BadParameter(f"Unknown parish {code}")
    as_admin = roles is None
    temp: str | None = None
    try:
        with tenant_session_scope(tenant) as tsession:
            if as_admin and not password:
                user, temp = create_initial_admin(
                    tsession, tenant, username=username, full_name=full_name, email=email
                )
            else:
                user = create_user(
                    tsession,
                    username=username,
                    full_name=full_name,
                    email=email,
                    password=password or (generate_token(18) + "-Aa1"),
                    must_change_password=not password,
                    enforce_policy=bool(password),
                )
                if not password:
                    temp = None if email else "(set via emailed link)"
                    if email:
                        send_reset_link(tsession, tenant, user, None, invite=True)
                for role_code in [ADMIN_ROLE] if as_admin else roles or []:
                    role = role_by_code(tsession, role_code)
                    if role is None:
                        raise typer.BadParameter(f"Unknown role {role_code}")
                    assign_role(tsession, user, role, remarks="assigned via ps-admin")
    except AppError as exc:
        details = "; ".join(d["message"] for d in exc.details)
        raise typer.BadParameter(f"{exc.message}{': ' + details if details else ''}") from exc
    typer.echo(f"user {username.lower()} created in {tenant.code}")
    if temp and not temp.startswith("("):
        typer.echo(f"temporary password (must be changed at first login): {temp}")
    elif email and not password:
        typer.echo(f"a set-password link was emailed to {email}")


@app.command("create-parish-user")
def create_parish_user(
    parish: Annotated[str, typer.Option(help="Parish code")],
    username: Annotated[str, typer.Option()],
    full_name: Annotated[str, typer.Option("--name")],
    email: Annotated[str | None, typer.Option()] = None,
    password: Annotated[
        str | None, typer.Option(help="Omit to email a set-password link (needs --email)")
    ] = None,
    role: Annotated[
        list[str] | None, typer.Option("--role", help="Parish-wide role code (repeatable)")
    ] = None,
) -> None:
    """Create a user inside a parish database, optionally with parish-wide roles."""
    if not password and not email:
        raise typer.BadParameter("Provide --password or --email")
    _create_admin(parish, username, full_name, email, password, roles=[r.upper() for r in role or []])


if __name__ == "__main__":
    app()


@app.command("workflow-sla")
def workflow_sla(
    only: Annotated[list[str] | None, typer.Option("--only", help="Parish code(s)")] = None,
) -> None:
    """Send reminders for overdue approval tasks and escalate them (normally run by Celery beat)."""
    from app.modules.workflow.tasks import run_sla_sweep

    for code, r in run_sla_sweep(only).items():
        typer.echo(f"{code}: {r['reminded']} reminded, {r['escalated']} escalated")


@app.command("reminders")
def reminders(
    only: Annotated[list[str] | None, typer.Option("--only", help="Parish code(s)")] = None,
) -> None:
    """Send meeting and action-item reminders now (normally run hourly by Celery beat)."""
    from app.modules.activities.tasks import run_all_reminders

    for code, r in run_all_reminders(only).items():
        typer.echo(
            f"{code}: {r['meetings']} meeting reminder(s), {r['action_items']} action item reminder(s)"
        )


@app.command("publish-notices")
def publish_notices(
    only: Annotated[list[str] | None, typer.Option("--only", help="Parish code(s)")] = None,
) -> None:
    """Publish approved notices whose time has come (normally run every 10 minutes by Celery beat)."""
    from app.modules.notices.tasks import run_publish_due

    for code, n in run_publish_due(only).items():
        typer.echo(f"{code}: {n} notice(s) published")

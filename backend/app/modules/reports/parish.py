"""Parish registers: families, members, Anbiyam-wise, organisation membership, sacraments, marriages."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select

from app.modules.org_units.models import OrgUnit, OrgUnitType
from app.modules.people import service as people
from app.modules.people.models import Family, Member, OrgUnitMembership

from .base import ORG_UNIT, Col, Ctx, Param, Result, report

FAMILY_STATUS = Param(
    "status",
    (
        ("ACTIVE", "Active"),
        ("PENDING_ANBIYAM", "Waiting for an Anbiyam"),
        ("INACTIVE", "Inactive"),
        ("TRANSFERRED_OUT", "Transferred out"),
    ),
)
MEMBER_STATUS = Param(
    "status",
    (
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("DECEASED", "Deceased"),
        ("TRANSFERRED_OUT", "Transferred out"),
    ),
    default="ACTIVE",
)
GENDER = Param("gender", (("M", "Male"), ("F", "Female")))
SACRAMENT = Param(
    "sacrament",
    (("BAPTISM", "Baptism"), ("COMMUNION", "First Holy Communion"), ("CONFIRMATION", "Confirmation")),
    default="BAPTISM",
)


def _name(m: Member) -> str:
    return " ".join(p for p in (m.first_name, m.last_name) if p)


def _age(dob: date | None) -> int | None:
    if dob is None:
        return None
    t = date.today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def _anbiyam_names(ctx: Ctx) -> dict[int, str]:
    return dict(ctx.db.execute(select(OrgUnit.id, OrgUnit.name)).all())


def _families(ctx: Ctx) -> list[Family]:
    stmt = select(Family).where(Family.is_deleted.is_(False), people.family_scope(ctx.scope))
    if ctx.p.status:
        stmt = stmt.where(Family.status == ctx.p.status)
    else:
        stmt = stmt.where(Family.status.in_(("ACTIVE", "PENDING_ANBIYAM")))
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(Family.anbiyam_id == u.id)
    return list(ctx.db.scalars(stmt))


def _head(f: Family) -> str:
    head = next((m for m in f.members if m.id == f.head_member_id), None)
    return _name(head) if head else ""


def _family_row(f: Family, names: dict[int, str]) -> dict[str, Any]:
    live = [m for m in f.members if not m.is_deleted and m.status == "ACTIVE"]
    return {
        "code": f.code,
        "family": f.family_name,
        "head": _head(f),
        "anbiyam": names.get(f.anbiyam_id or 0, ""),
        "members": len(live),
        "phone": f.phone,
        "address": ", ".join(x for x in (f.address_line1, f.city) if x),
        "registered_on": f.registered_on,
        "status": f.status,
    }


@report(
    "family_register", "PARISH", "Family register",
    "Every family with head, Anbiyam, members, contact and registration date.",
    "family.view", (ORG_UNIT, FAMILY_STATUS),
)  # fmt: skip
def family_register(ctx: Ctx) -> Result:
    names = _anbiyam_names(ctx)
    rows = sorted((_family_row(f, names) for f in _families(ctx)), key=lambda r: r["code"])
    return Result(
        [
            Col("code", "Code"),
            Col("family", "Family"),
            Col("head", "Head"),
            Col("anbiyam", "Anbiyam"),
            Col("members", "Members", "number"),
            Col("phone", "Phone"),
            Col("address", "Address"),
            Col("registered_on", "Registered", "date"),
            Col("status", "Status", "status"),
        ],
        rows,
        subtitle=f"{len(rows)} families · {sum(r['members'] for r in rows)} members",
    )


@report(
    "anbiyam_register", "PARISH", "Anbiyam-wise family register",
    "Families grouped by Anbiyam, with a count per Anbiyam.",
    "family.view", (ORG_UNIT,),
)  # fmt: skip
def anbiyam_register(ctx: Ctx) -> Result:
    names = _anbiyam_names(ctx)
    rows = sorted(
        (_family_row(f, names) for f in _families(ctx)),
        key=lambda r: (r["anbiyam"] == "", r["anbiyam"], r["family"]),
    )
    for r in rows:
        r["anbiyam"] = r["anbiyam"] or "— No Anbiyam yet —"
    per = {}
    for r in rows:
        per[r["anbiyam"]] = per.get(r["anbiyam"], 0) + 1
    return Result(
        [
            Col("anbiyam", "Anbiyam"),
            Col("code", "Code"),
            Col("family", "Family"),
            Col("head", "Head"),
            Col("members", "Members", "number"),
            Col("phone", "Phone"),
        ],
        rows,
        subtitle=" · ".join(f"{k}: {v}" for k, v in per.items()),
        totals={
            "anbiyam": "Total",
            "family": f"{len(rows)} families",
            "members": sum(r["members"] for r in rows),
        },
    )


@report(
    "member_register", "PARISH", "Member register",
    "Members with family, Anbiyam and relationship. Age and phone need permission to view personal details.",
    "member.view", (ORG_UNIT, MEMBER_STATUS, GENDER),
)  # fmt: skip
def member_register(ctx: Ctx) -> Result:
    sensitive = ctx.auth.permissions.scope("member.view_sensitive").granted
    stmt = (
        select(Member)
        .join(Family, Family.id == Member.family_id)
        .where(Member.is_deleted.is_(False), Family.is_deleted.is_(False), people.family_scope(ctx.scope))
        .order_by(Family.code, Member.id)
    )
    stmt = stmt.where(Member.status == (ctx.p.status or "ACTIVE"))
    if ctx.p.gender:
        stmt = stmt.where(Member.gender == ctx.p.gender)
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(Family.anbiyam_id == u.id)
    names = _anbiyam_names(ctx)
    rows = []
    for m in ctx.db.scalars(stmt):
        rows.append(
            {
                "code": m.code,
                "name": _name(m),
                "gender": {"M": "Male", "F": "Female"}.get(m.gender, m.gender),
                "relationship": m.relationship_to_head.replace("_", " ").title(),
                "age": _age(m.date_of_birth) if sensitive else None,
                "phone": m.phone if sensitive else None,
                "family_code": m.family.code,
                "family": m.family.family_name,
                "anbiyam": names.get(m.family.anbiyam_id or 0, ""),
                "status": m.status,
            }
        )
    cols = [
        Col("code", "Code"),
        Col("name", "Name"),
        Col("gender", "Gender"),
        Col("relationship", "Relationship"),
        *([Col("age", "Age", "number"), Col("phone", "Phone")] if sensitive else []),
        Col("family_code", "Family code"),
        Col("family", "Family"),
        Col("anbiyam", "Anbiyam"),
        Col("status", "Status", "status"),
    ]
    return Result(cols, rows, subtitle=f"{len(rows)} members")


@report(
    "org_membership", "PARISH", "Organisation membership",
    "Current members of societies, Sabai, committees and other organisations.",
    "org_unit.view", (Param("org_type"), ORG_UNIT),
)  # fmt: skip
def org_membership(ctx: Ctx) -> Result:
    stmt = (
        select(OrgUnitMembership, OrgUnit, OrgUnitType)
        .join(OrgUnit, OrgUnit.id == OrgUnitMembership.org_unit_id)
        .join(OrgUnitType, OrgUnitType.id == OrgUnit.type_id)
        .where(
            OrgUnitMembership.left_on.is_(None),
            OrgUnit.is_deleted.is_(False),
            ctx.scope.filter(OrgUnit.id),
        )
    )
    if ctx.p.org_type:
        stmt = stmt.where(OrgUnitType.code == ctx.p.org_type)
    if (u := ctx.unit()) is not None:
        stmt = stmt.where(OrgUnit.id == u.id)
    rows = []
    for ms, unit, ty in ctx.db.execute(stmt).all():
        if ms.member_id:
            m = ctx.db.get(Member, ms.member_id)
            who, code, fam = (_name(m), m.code, m.family.family_name) if m else ("", "", "")
        else:
            f = ctx.db.get(Family, ms.family_id)
            who, code, fam = (f.family_name, f.code, f.family_name) if f else ("", "", "")
        rows.append(
            {
                "type": ty.name,
                "organisation": unit.name,
                "name": who,
                "code": code,
                "family": fam,
                "joined_on": ms.joined_on,
            }
        )
    rows.sort(key=lambda r: (r["type"], r["organisation"], r["name"]))
    per: dict[str, int] = {}
    for r in rows:
        per[r["organisation"]] = per.get(r["organisation"], 0) + 1
    return Result(
        [
            Col("type", "Type"),
            Col("organisation", "Organisation"),
            Col("name", "Member"),
            Col("code", "Code"),
            Col("family", "Family"),
            Col("joined_on", "Joined", "date"),
        ],
        rows,
        subtitle=" · ".join(f"{k}: {v}" for k, v in per.items()) or None,
    )


_SACRAMENT_COLS = {
    "BAPTISM": (Member.baptism_date, Member.baptism_place, Member.baptism_register_ref),
    "COMMUNION": (Member.communion_date, Member.communion_place, None),
    "CONFIRMATION": (Member.confirmation_date, Member.confirmation_place, None),
    "MARRIAGE": (Member.marriage_date, Member.marriage_place, Member.marriage_register_ref),
}


def _sacrament(ctx: Ctx, kind: str) -> Result:
    when, place, ref = _SACRAMENT_COLS[kind]
    lo, hi = ctx.range("all")
    stmt = (
        select(Member)
        .join(Family, Family.id == Member.family_id)
        .where(Member.is_deleted.is_(False), when.is_not(None))
        .order_by(when, Member.id)
    )
    if lo:
        stmt = stmt.where(when >= lo)
    if hi:
        stmt = stmt.where(when <= hi)
    rows = [
        {
            "date": getattr(m, when.key),
            "name": _name(m),
            "code": m.code,
            "gender": {"M": "Male", "F": "Female"}.get(m.gender, m.gender),
            "family": f"{m.family.family_name} ({m.family.code})",
            "place": getattr(m, place.key),
            "ref": getattr(m, ref.key) if ref is not None else None,
        }
        for m in ctx.db.scalars(stmt)
    ]
    cols = [
        Col("date", "Date", "date"),
        Col("name", "Name"),
        Col("code", "Member code"),
        Col("gender", "Gender"),
        Col("family", "Family"),
        Col("place", "Place"),
        *([Col("ref", "Register ref.")] if ref is not None else []),
    ]
    return Result(cols, rows, subtitle=f"{ctx.range_label(lo, hi)} · {len(rows)} entries")


@report(
    "sacrament_register", "PARISH", "Sacramental register",
    "Baptisms, first Holy Communions or confirmations recorded on member profiles.",
    "sacrament.view", (SACRAMENT, Param("date_range")), parish_wide=True,
)  # fmt: skip
def sacrament_register(ctx: Ctx) -> Result:
    kind = ctx.p.sacrament or "BAPTISM"
    if kind not in ("BAPTISM", "COMMUNION", "CONFIRMATION"):
        kind = "BAPTISM"
    return _sacrament(ctx, kind)


@report(
    "marriage_register", "PARISH", "Marriage register",
    "Marriages recorded on member profiles, with place and register reference.",
    "sacrament.view", (Param("date_range"),), parish_wide=True,
)  # fmt: skip
def marriage_register(ctx: Ctx) -> Result:
    return _sacrament(ctx, "MARRIAGE")

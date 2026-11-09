"""Regenerate docs/11-permission-matrix.md from the RBAC catalog: python scripts/gen_permission_matrix.py"""

from __future__ import annotations

from pathlib import Path

from app.modules.rbac.catalog import PERMISSION_CATALOG, SYSTEM_ROLES

ABBR = {
    "PARISH_ADMIN": "Adm",
    "PARISH_PRIEST": "Pri",
    "PARISH_PRESIDENT": "Pre",
    "PARISH_SECRETARY": "Sec",
    "PARISH_TREASURER": "Tre",
    "COMMITTEE_PRESIDENT": "CPr",
    "COMMITTEE_SECRETARY": "CSe",
    "COMMITTEE_TREASURER": "CTr",
    "ANBIYAM_LEADER": "Anb",
    "SABAI_LEADER": "Sab",
    "SOCIETY_LEADER": "Soc",
    "REVIEWER": "Rev",
    "APPROVER": "App",
    "GENERAL_MEMBER": "Mem",
    "FAMILY_ACCOUNT": "Fam",
}


def main() -> None:
    lines = [
        "# 11 — Role & Permission Matrix",
        "",
        "_Generated from `backend/app/modules/rbac/catalog.py` by `backend/scripts/gen_permission_matrix.py`._",
        "These are the **default** grants seeded into every new parish; parish administrators can edit them.",
        "",
        "## Roles",
        "",
        "| Abbr | Code | Name | Scope | Description |",
        "|---|---|---|---|---|",
    ]
    for r in SYSTEM_ROLES:
        lines.append(f"| {ABBR[r.code]} | `{r.code}` | {r.name} | {r.scope_type} | {r.description} |")
    lines += [
        "",
        "Scope: **PARISH** = parish-wide only; **ORG_UNIT** = assigned for one organisation unit and applies only "
        "to that unit's records; **ANY** = either. Super Administrator and Diocese Administrator are platform "
        "roles (master database) and never exist inside a parish.",
        "",
        "## Matrix",
        "",
        "| Permission | " + " | ".join(ABBR[r.code] for r in SYSTEM_ROLES) + " |",
        "|---|" + "---|" * len(SYSTEM_ROLES),
    ]
    for module, actions in PERMISSION_CATALOG.items():
        for action, desc in actions.items():
            code = f"{module}.{action}"
            cells = " | ".join("✓" if code in r.permissions else "" for r in SYSTEM_ROLES)
            lines.append(f"| `{code}` — {desc} | {cells} |")
    out = Path(__file__).resolve().parents[2] / "docs" / "11-permission-matrix.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

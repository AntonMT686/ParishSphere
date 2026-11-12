"""Permission catalog and default (system) roles.

The catalog is code; the database holds the parish's *configured* copy. Seeding (idempotent) inserts
missing permissions and roles. When a new permission is introduced in a later release, it is granted
to the system roles whose defaults include it — administrator customisations are otherwise preserved.

Platform roles (Super Administrator, Diocese Administrator) live in the master database
(``platform_users``) and never inside a parish database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# module → actions. Permission code = "<module>.<action>".
PERMISSION_CATALOG: dict[str, dict[str, str]] = {
    "user": {
        "view": "View user accounts",
        "create": "Create user accounts",
        "update": "Edit, activate, deactivate and unlock users",
        "delete": "Delete (archive) user accounts",
        "assign_role": "Assign and remove user roles",
    },
    "role": {"view": "View roles and permissions", "manage": "Create, edit and delete roles"},
    "settings": {"view": "View parish settings", "update": "Change parish settings"},
    "audit": {"view": "View the audit log", "export": "Export the audit log"},
    "org_unit": {
        "view": "View organisations (council, committees, Anbiyam, Sabai, societies)",
        "create": "Create organisations",
        "update": "Edit organisations",
        "delete": "Archive organisations",
        "manage_members": "Manage members and office bearers",
    },
    "family": {
        "view": "View families",
        "create": "Register families",
        "update": "Edit families",
        "delete": "Archive families",
        "transfer": "Transfer, merge and split families",
        "export": "Export family registers",
    },
    "member": {
        "view": "View members",
        "view_sensitive": "View sensitive member details (DOB, contacts, sacraments)",
        "create": "Add members",
        "update": "Edit members",
        "delete": "Archive members",
        "export": "Export member registers",
    },
    "sacrament": {
        "view": "View sacramental registers",
        "create": "Record sacramental entries",
        "update": "Edit sacramental entries",
        "export": "Export sacramental registers",
    },
    "priest": {"view": "View priests", "create": "Add priests", "update": "Edit priests and assignments"},
    "activity": {
        "view": "View activities",
        "create": "Record activities",
        "update": "Edit activities",
        "delete": "Delete draft activities",
        "submit": "Submit activities for approval",
        "review": "Review activities",
        "approve": "Approve activities",
        "reject": "Reject activities",
        "export": "Export activities",
    },
    "meeting": {
        "view": "View meetings and minutes",
        "create": "Schedule meetings and record minutes",
        "update": "Edit meetings and minutes",
        "delete": "Cancel or delete draft meetings",
        "submit": "Submit minutes for approval",
        "review": "Review minutes",
        "approve": "Approve minutes",
        "reject": "Reject minutes",
        "export": "Export meeting reports",
    },
    "action_item": {
        "view": "View action items",
        "create": "Create action items",
        "update": "Update action items",
    },
    "workflow": {"view": "View workflow configuration", "manage": "Configure approval workflows"},
    "finance": {
        "view_summary": "View financial summaries",
        "view": "View financial transactions",
        "create": "Enter financial transactions",
        "update": "Edit draft transactions",
        "delete": "Void draft transactions",
        "submit": "Submit transactions for approval",
        "review": "Review transactions",
        "approve": "Approve transactions",
        "reject": "Reject transactions",
        "export": "Export financial reports",
    },
    "finance_period": {
        "view": "View monthly periods and statements",
        "submit": "Close a month and submit the statement",
        "approve": "Approve monthly statements",
        "release": "Release (publish and lock) monthly statements",
    },
    "notice": {
        "view": "View notices",
        "create": "Prepare notices",
        "update": "Edit notices",
        "delete": "Delete draft notices",
        "submit": "Submit notices for approval",
        "review": "Review notices",
        "approve": "Approve notices",
        "reject": "Reject notices",
        "publish": "Publish and archive notices",
    },
    "document": {
        "view": "View documents",
        "view_confidential": "View confidential documents",
        "create": "Upload documents",
        "update": "Edit document metadata and versions",
        "delete": "Archive documents",
        "export": "Download documents in bulk",
    },
    "report": {"view": "View reports", "export": "Export reports"},
}

ALL_PERMISSIONS: frozenset[str] = frozenset(
    f"{m}.{a}" for m, acts in PERMISSION_CATALOG.items() for a in acts
)


def _perms(*patterns: str) -> frozenset[str]:
    """Expand patterns: ``family.*`` (module wildcard), ``*.view`` (action wildcard) or exact codes."""
    out: set[str] = set()
    for p in patterns:
        module, _, action = p.partition(".")
        matched = {
            code
            for code in ALL_PERMISSIONS
            if (module == "*" or code.split(".")[0] == module)
            and (action == "*" or code.split(".")[1] == action)
        }
        if not matched:
            raise ValueError(f"Permission pattern {p!r} matches nothing")
        out |= matched
    return frozenset(out)


PARISH, ORG_UNIT, ANY = "PARISH", "ORG_UNIT", "ANY"


@dataclass(frozen=True)
class RoleDef:
    code: str
    name: str
    scope_type: str  # PARISH: parish-wide only · ORG_UNIT: must be scoped to an org unit · ANY: either
    description: str
    permissions: frozenset[str] = field(default_factory=frozenset)


_ORG_WORK = (
    "activity.view",
    "activity.create",
    "activity.update",
    "activity.delete",
    "activity.submit",
    "meeting.view",
    "meeting.create",
    "meeting.update",
    "meeting.delete",
    "meeting.submit",
    "action_item.*",
    "org_unit.view",
    "member.view",
    "family.view",
    "notice.view",
    "document.view",
    "document.create",
)

SYSTEM_ROLES: tuple[RoleDef, ...] = (
    RoleDef(
        "PARISH_ADMIN",
        "Parish Administrator",
        PARISH,
        "Configures users, roles, workflows, organisations and settings.",
        _perms(
            "user.*",
            "role.*",
            "settings.*",
            "audit.*",
            "org_unit.*",
            "workflow.*",
            "priest.*",
            "family.view",
            "family.create",
            "family.update",
            "family.export",
            "member.view",
            "member.create",
            "member.update",
            "member.export",
            "*.view",
            "report.*",
            "document.create",
            "document.update",
        )
        - {"finance.view", "sacrament.view", "finance_period.view"},
    ),
    RoleDef(
        "PARISH_PRIEST",
        "Parish Priest",
        PARISH,
        "Final authority: full visibility and final approval on every workflow.",
        ALL_PERMISSIONS - _perms("user.delete", "role.manage"),
    ),
    RoleDef(
        "PARISH_PRESIDENT",
        "Parish President",
        PARISH,
        "Leads the parish council; reviews committee work.",
        _perms(
            "*.view",
            "*.review",
            "activity.export",
            "activity.create",
            "activity.update",
            "activity.submit",
            "meeting.export",
            "report.*",
            "action_item.*",
            "meeting.create",
            "meeting.update",
            "meeting.submit",
            "notice.create",
            "notice.update",
            "notice.submit",
        )
        - _perms("sacrament.view", "user.view", "role.view", "audit.view"),
    ),
    RoleDef(
        "PARISH_SECRETARY",
        "Parish Secretary",
        PARISH,
        "Maintains parish registers, meetings and notices.",
        _perms(
            "family.*",
            "member.*",
            "sacrament.*",
            "meeting.*",
            "action_item.*",
            "activity.view",
            "activity.review",
            "activity.export",
            "activity.create",
            "activity.update",
            "activity.submit",
            "activity.delete",
            "notice.view",
            "notice.create",
            "notice.update",
            "notice.delete",
            "notice.submit",
            "notice.review",
            "org_unit.view",
            "priest.view",
            "document.view",
            "document.create",
            "document.update",
            "report.*",
            "workflow.view",
            "finance.view_summary",
        ),
    ),
    RoleDef(
        "PARISH_TREASURER",
        "Parish Treasurer",
        PARISH,
        "Maintains parish accounts and prepares monthly statements.",
        _perms(
            "finance.*",
            "finance_period.view",
            "finance_period.submit",
            "family.view",
            "org_unit.view",
            "activity.view",
            "notice.view",
            "document.view",
            "document.create",
            "report.*",
            "workflow.view",
        )
        - {"finance.approve"},
    ),
    RoleDef(
        "COMMITTEE_PRESIDENT",
        "Committee President",
        ORG_UNIT,
        "Leads an organisation unit; reviews its activities and minutes.",
        _perms(
            *_ORG_WORK,
            "activity.review",
            "meeting.review",
            "finance.view_summary",
            "finance.review",
            "org_unit.manage_members",
        ),
    ),
    RoleDef(
        "COMMITTEE_SECRETARY",
        "Committee Secretary",
        ORG_UNIT,
        "Records activities, meetings and minutes of an organisation unit.",
        _perms(*_ORG_WORK),
    ),
    RoleDef(
        "COMMITTEE_TREASURER",
        "Committee Treasurer",
        ORG_UNIT,
        "Enters financial transactions of an organisation unit.",
        _perms(
            "finance.view_summary",
            "finance.view",
            "finance.create",
            "finance.update",
            "finance.delete",
            "finance.submit",
            "org_unit.view",
            "activity.view",
            "member.view",
            "notice.view",
            "document.view",
            "document.create",
        ),
    ),
    RoleDef(
        "ANBIYAM_LEADER",
        "Anbiyam Leader",
        ORG_UNIT,
        "Leads an Anbiyam: its families, meetings and activities.",
        _perms(
            *_ORG_WORK,
            "family.update",
            "member.update",
            "member.create",
            "activity.review",
            "meeting.review",
            "org_unit.manage_members",
        ),
    ),
    RoleDef(
        "SABAI_LEADER",
        "Sabai Leader",
        ORG_UNIT,
        "Leads a Sabai / congregation.",
        _perms(*_ORG_WORK, "activity.review", "meeting.review", "org_unit.manage_members"),
    ),
    RoleDef(
        "SOCIETY_LEADER",
        "Society Leader",
        ORG_UNIT,
        "Leads a society or association.",
        _perms(*_ORG_WORK, "activity.review", "meeting.review", "org_unit.manage_members"),
    ),
    RoleDef(
        "REVIEWER",
        "Reviewer",
        ANY,
        "Generic reviewer used in workflows.",
        _perms("*.review", "activity.view", "meeting.view", "finance.view", "notice.view", "document.view"),
    ),
    RoleDef(
        "APPROVER",
        "Approver",
        ANY,
        "Generic approver used in workflows.",
        _perms(
            "*.approve",
            "*.reject",
            "activity.view",
            "meeting.view",
            "finance.view",
            "notice.view",
            "finance_period.view",
            "document.view",
        ),
    ),
    RoleDef(
        "GENERAL_MEMBER",
        "General Member",
        PARISH,
        "Parishioner with a personal login.",
        _perms("notice.view"),
    ),
    RoleDef(
        "FAMILY_ACCOUNT",
        "Family Account User",
        PARISH,
        "Family portal account (phase 2).",
        _perms("notice.view"),
    ),
)

SYSTEM_ROLE_CODES = frozenset(r.code for r in SYSTEM_ROLES)
ADMIN_ROLE = "PARISH_ADMIN"
# Permissions the administrator role may never lose (prevents locking everyone out of user management).
ADMIN_LOCKED_PERMISSIONS = frozenset(
    {"user.view", "user.update", "user.assign_role", "role.view", "role.manage"}
)

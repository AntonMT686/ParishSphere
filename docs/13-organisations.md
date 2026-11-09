# 13 — Configurable Organisations (T7)

Parish Council (Peravai), Committees, Anbiyam, Sabai, Societies and Associations are **data, not code**.

## Model

| Table | Purpose |
|---|---|
| `org_unit_types` | Kind of organisation: names (English/Tamil, singular/plural), who joins (`MEMBER` or `FAMILY`), `membership_rules` (age/gender/limit, enforced when members join – T8), whether several may exist (Council: one per parish), code prefix |
| `org_unit_positions` | Offices within a type (President, Secretary, …), the **role** each grants, max holders (empty = unlimited) |
| `org_units` | The actual organisations, as a tree (`parent_id`, e.g. Anbiyam zone → groups); `ACTIVE`/`INACTIVE`; soft-deleted only when created by mistake and without history |
| `org_unit_office_bearers` | Who held which position when (`valid_from`/`valid_to`, `ended_at`); never deleted |

Seeded per parish (idempotent; parish edits are kept): COUNCIL, COMMITTEE, ANBIYAM (families join), SABAI, SOCIETY, ASSOCIATION, each with President/Secretary/Treasurer and other positions.

## Office bearers → roles (how workflows find reviewers)

Appointing a **user** to a position that maps to a role creates a role assignment:
- roles of scope `ORG_UNIT`/`ANY` (Society Leader, Committee Secretary, …) are scoped to that organisation;
- `PARISH` roles (Council President → Parish President, Council Secretary → Parish Secretary, Council Treasurer → Parish Treasurer) are parish-wide.

Ending the term ends that assignment, and the history remains. Office bearers without a login can be recorded by name, but no role is granted to them.

Roles held for an organisation **apply to its sub-units**. A zone leader therefore sees and reviews every Anbiyam group in the zone, and `users_with_permission(code, unit)` includes holders on parent units.

## Authorization

| Action | Permission |
|---|---|
| List/view units | `org_unit.view`. Scoped holders see only their units and sub-units; other units return 404 |
| Create / archive / activate / delete units, move units | parish-wide `org_unit.create` / `org_unit.delete` |
| Edit unit details | `org_unit.update` for that unit |
| Appoint / end office bearers | `org_unit.manage_members` for that unit (e.g. a Society President for their society). Appointing to a position that grants a **parish-wide** role also needs `user.assign_role`. Nobody can appoint themselves to a role-granting position |
| Types & positions | parish-wide `org_unit.create` / `update` / `delete`; system types cannot be deleted |
| User picker | `GET /api/v1/users/lookup?q=`: names only; needs `user.view` or `org_unit.manage_members` |

## API

`/api/v1/org-unit-types` (list/get/create/update/delete; `/positions` add/update/delete) · `/api/v1/org-units` (list with `type`, `q`, `status`, `parent`=id|`root`, paging/sort; create; get; update; `/archive`; `/activate`; delete) · `/api/v1/org-units/{id}/office-bearers` (list `?include_history=`, appoint; `/{bearer}/end`). Role assignments through `/api/v1/users/{id}/roles` accept `org_unit_id`.

## UI

The Organisations menu is generated from the configured types, using Tamil names when Tamil is selected. Each type has a list page (`/org/<type>`). The detail page (`/org/units/<id>`) shows details, office bearers with history, appoint/end-term actions and sub-units. **Administration → Organisation Types** is where types, positions and role mappings are configured. The user drawer can assign roles for a chosen organisation.

Members and families joining organisations arrive with the member registry (T8).

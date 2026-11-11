# 14 — Families & Members (T8)

The parish register. Every change keeps history; nothing that happened in real life is ever deleted.

## Model

| Table | Purpose |
|---|---|
| `families` | `FAM000123`, names (English/Tamil), Anbiyam, address, phone, status (`ACTIVE`, `PENDING_ANBIYAM`, `INACTIVE`, `TRANSFERRED_OUT`, `MERGED`), previous parish, `head_member_id`, `merged_into_id` |
| `members` | `MEM000456`, family, names, gender, date of birth, relationship to head, contacts, education/occupation, marital status, status (`ACTIVE`, `INACTIVE`, `DECEASED`, `TRANSFERRED_OUT`), date of death, sacramental summary (baptism, first communion, confirmation, marriage: date, place, register no.) |
| `family_anbiyam_history` | Which Anbiyam a family belonged to, when |
| `member_family_history` | Which family a member belonged to, when, and why (`REGISTERED`, `ADDED`, `MOVED`, `SPLIT`, `MERGE`) |
| `family_events` | Timeline shown on the family page (registered, Anbiyam changed, head changed, member added/moved/removed, death, status, transfer out, merge, split) |
| `org_unit_memberships` | A member (or, for family-based types, a family) belonging to an organisation; ended, never deleted |

Names and phone numbers are stored normalised as well (`search_name`, `phone_digits`). This supports search and duplicate detection, and works for Tamil text too.

## Rules

- **Registration:**
  - A family is registered together with its members, and exactly one member must be **HEAD**.
  - Without an Anbiyam the family is `PENDING_ANBIYAM`.
- **Duplicate detection:**
  - A family is flagged if another family has the same phone or the same family name.
  - It is also flagged if any of its members has the same name and date of birth, or the same phone, as an existing member.
  - The API answers `409 DUPLICATE_SUSPECTED` until the user confirms with `confirm_not_duplicate`.
  - The registration form checks before submitting and shows the matching families with their reasons.
- **Head of family:**
  - Setting a new head demotes **every** other member still marked HEAD (including a deceased former head) to the chosen relationship.
  - If the head moves to another family or is split off, a new head for the remaining members is required (`FAMILY_HEAD_REQUIRED`).
  - When the head dies, the family is left without a head and the UI asks for a new one.
- **Moves:**
  - Merge: all members go to the surviving family, and the source becomes `MERGED`.
  - Split: chosen members form a new family. It inherits the address and Anbiyam unless others are chosen.
  - Transfer out: the family and its active members become `TRANSFERRED_OUT`, and their memberships end.
  - Merged or transferred families accept no further changes.
- **Deceased / inactive:** organisation memberships end. Delete is only for members entered by mistake.
- **Organisation memberships:**
  - The type's `membership_rules` are enforced: `min_age`, `max_age` (a date of birth is then required), `genders`, and `max_units_per_member`.
  - Anbiyam membership *is* the family's Anbiyam, changed from the family record.

## Access

| Permission | Effect |
|---|---|
| `family.view`, `member.view` | View; Anbiyam-scoped holders (Anbiyam leaders) only see families of their Anbiyam and its sub-units. Others get 404 |
| `family.create` / `update` / `transfer` / `export` | Register; edit, set head, status; change Anbiyam, merge, split, transfer out, move members; export registers |
| `member.create` / `update` / `delete` / `export` | Add; edit, deceased, status; remove a mistaken entry; export |
| `member.view_sensitive` | Date of birth, phone, email, education, occupation, marital status, remarks. Anyone adding a member may *enter* these, but only holders may see or change them later. Everyone with `member.view` sees the **age** |
| `sacrament.view` / `sacrament.update` | See / record sacramental details |

## API

- `/api/v1/families`:
  - list (`q` matches code, family or member name in English or Tamil, or phone; also `anbiyam` (id or `none`), `status`, registration dates)
  - `POST /check-duplicates`, create, `/export`
  - `GET/PATCH /{id}`
  - `/{id}/members`, `/{id}/anbiyam`, `/{id}/head`, `/{id}/status`, `/{id}/transfer-out`, `/{id}/merge`, `/{id}/split`, `/{id}/history`
- `/api/v1/members`:
  - list (`q`, `gender`, `status`, `anbiyam`, `age_min`/`age_max`), `/export`
  - `GET/PATCH /{id}`, `/{id}/deceased`, `/{id}/status`, `/{id}/move`, `DELETE /{id}`, `/{id}/memberships`
- `/api/v1/org-units/{id}/memberships`: list (families for an Anbiyam), add, `/{membership}/end`
- Office bearers can be linked to a register member (`member_id`).

## UI

- **Families:** list with search, Anbiyam and status filters, and export.
- **Register family:** 4 steps (family, address, members with head selection, then Anbiyam and the duplicate check).
- **Family page:** members table, details, history timeline. Actions: add member, edit, change Anbiyam, set head, split, merge, transfer out, (de)activate.
- **Member panel:** details with sensitive and sacrament sections gated by permission, edit, move to another family, record death, (de)activate, remove, organisations.
- **Members:** list with search, gender, status and age filters, plus export.
- **Organisation page:** members card with add/end membership. For an Anbiyam it lists the families.

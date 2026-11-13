# 20 — Global Search, Reports & Audit Viewer (T15)

## Global search

`GET /api/v1/search?q=…[&group=…&limit=…]` takes at least 2 characters and returns matches grouped by record type. Every group applies the same permission and scope as its own list page, so search never reveals a record that its list would hide.

| Group | Permission (scope) | Matches on |
|---|---|---|
| families | `family.view` (Anbiyam-scoped) | code, name (normalised, Tamil name), phone |
| members | `member.view` (through the family's Anbiyam) | code, name, Tamil name, phone |
| organisations | `org_unit.view` | name, code, Tamil name |
| activities | `activity.view` (organisation-scoped) | title, code, location |
| meetings | `meeting.view` (organisation-scoped) | title, code, location |
| finance | `finance.view` (organisation-scoped) | entry code, particulars, payer/payee, reference no. |
| notices | `notice.view`; live notices for the user's audience, plus notices the user manages | title, code, Tamil title |
| users | `user.view` (parish-wide) | name, username, email |

- Each group returns its total and the first few matches, with an exact code match first.
- Each match links to its record. Members open on their family page with the member panel open (`/families/{id}?member={id}`).
- Users open in the users list (`/admin/users?open={id}`).

**UI**
- The search box in the top bar is focused with **Ctrl+K** or **/**.
- Results appear in a dropdown grouped by type. Arrow keys and Enter open a result; Enter with nothing selected opens the full results page.
- The dropdown never shows results for earlier text while a new search is loading.
- **/search?q=** shows every group as a card, with *Show all* (up to 50 per group).

## Reports

The reports module is in `app/modules/reports/`. Each report declares:
- its parameters;
- the **data permission** behind it, checked with its scope;
- whether that permission must be parish-wide.

A report returns columns (text, number, money, date or status), rows and an optional totals row.

| Endpoint | Purpose |
|---|---|
| `GET /reports` | The reports this user may run (needs `report.view` plus each report's data permission), with their parameters and whether the user may export them |
| `GET /reports/{code}?…` | On-screen preview (first 500 rows; `truncated` flag) |
| `GET /reports/{code}/export?format=xlsx\|csv\|pdf&…` | Download. Needs `report.export`. Audited as `REPORT_EXPORTED`. Subject to the platform export row limit |

Parameters: `date_from`, `date_to`, `month` (YYYY-MM), `fy` (start year), `org_unit`, `org_type`, `status`, `sacrament`, `gender`. If no date range is given, it defaults to the financial year to date.

| Group | Report | Data permission |
|---|---|---|
| Parish | Family register | `family.view` (Anbiyam-scoped) |
| | Anbiyam-wise family register | `family.view` |
| | Member register (age and phone only with `member.view_sensitive`) | `member.view` |
| | Organisation membership, for society or Sabai membership via the type filter | `org_unit.view` |
| | Sacramental register (baptism / first Holy Communion / confirmation) | `sacrament.view` (parish-wide) |
| | Marriage register | `sacrament.view` (parish-wide) |
| Activity | Organisation-wise activities, also used for completed activities and parish council activities | `activity.view` |
| | Monthly activity summary | `activity.view` |
| | Meeting report (attendance, minutes, action items) | `meeting.view` |
| | Pending action items | `action_item.view` |
| | Activity participation | `activity.view` |
| Finance | Monthly income and expenditure | `finance.view` (organisation-scoped) |
| | Annual financial statement | `finance.view` |
| | Donation report | `finance.view` |
| | Expense category report | `finance.view` |
| | Organisation-wise financial statement | `finance.view` |
| | Pending financial approvals | `finance.view` |
| Management | Pending approvals | `workflow.view` (parish-wide) |
| | User activity | `audit.view` (parish-wide) |
| | Workflow turnaround time | `workflow.view` (parish-wide) |
| | Committee performance | `activity.view` |

Three reports from the brief wait for later phases:
- Festival budget vs actual: T19.
- Historical document statistics: T20.
- Diocese-level reports: T23.

**Permissions**
- Organisation leader roles (Committee President/Secretary, Anbiyam Leader, Sabai and Society leaders) now include `report.view` and `report.export` by default. Their reports cover only their own unit.
- **Existing parishes:** tick these two permissions for those roles under *Administration → Roles*. New defaults are not pushed to existing roles, so that administrators' own changes are kept.

**UI**
- **Reports**: a catalog grouped as Parish registers, Activities & meetings, Finance and Management.
- **Report page**:
  - filters, then *Run report*;
  - a table with a sticky header, right-aligned figures, rupee formatting and status badges;
  - a bold totals row;
  - an *Export* menu (Excel, CSV, PDF).
- Tamil titles and descriptions are included for every report.

## Audit viewer

`/admin/audit` (permission `audit.view`) is read-only.
- **Search** covers remarks, record id, username and full name.
- **Action** and **Module** are dropdowns filled from `GET /audit-logs/facets` (distinct modules, actions and record types).
- The **Record** column shows type · code.
- Clicking a row opens the old and new values side by side.
- Export (`audit.export`) produces XLSX, CSV or PDF.
- The *User activity* report summarises sign-ins, failed sign-ins and actions per user.

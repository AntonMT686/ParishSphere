# 19 — Role Dashboards (T14)

The dashboard follows the user's **permissions**, not their role names. One endpoint, `GET /api/v1/dashboard`, returns only the sections the user may see. Every figure is limited to the user's scope: an Anbiyam leader sees their own Anbiyam, and a society treasurer sees their society's money. Custom roles therefore get a sensible dashboard with no extra configuration.

| Section | Shown when the user has | Content |
|---|---|---|
| `approvals` | always | The user's own pending workflow tasks (overdue ones first), counts by record type, and how many are finance tasks |
| `people` | `family.view` (Anbiyam-scoped) | Families, active members, new families this month, families waiting for an Anbiyam, families and members per Anbiyam, age bands, gender split |
| `organisations` | `org_unit.view` | Per organisation type: active units and current members (or families, for Anbiyams) |
| `finance` | `finance.view` or `finance.view_summary` (organisation-scoped) | 12-month income and expense, income and expense by category for the financial year, donations this month and this financial year, entries awaiting approval. With parish-wide `finance_period.view`, also the status of the last six monthly statements |
| `activities` | `activity.view` | Upcoming and recently completed activities, activities in review, approved activities still awaiting a completion report, completed vs planned per organisation over the last 12 months |
| `meetings` | `meeting.view` | Upcoming meetings, minutes in review |
| `events` | everyone | Approved parish-level events in the next 60 days, plus events of the user's own organisations |
| `me` | the login is linked to a member (`users.member_id`) | The user's member code, family, Anbiyam, household, memberships, and the family's donations (last 8, and the total for this financial year) |

In practice:
- The **Parish Priest** sees everything.
- The **President and Secretary** see review queues, activity and meeting counters, and activity by organisation.
- The **Treasurer** sees the money charts and the statement timeline.
- An **Anbiyam leader** sees their own Anbiyam's numbers.
- A **parishioner** sees their family, donations, events and notices.

Budget vs actual waits for budgets (T19, Phase 2).

## UI

`features/dashboard`:
- **Stat cards**: families, members, Anbiyams, societies, pending approvals, pending finance. Each card links to its list page.
- **Approvals card**, **Upcoming events**.
- **Charts** (Recharts):
  - income vs expense (grouped bars);
  - income and expense by category, families by Anbiyam (horizontal bars);
  - members by age;
  - activities by organisation (stacked bars).
- **Donations & statements** timeline, **Organisations** list, activity counters and lists.
- **My family** and **My family's donations**.
- The existing **notices**, **finance summary**, **meetings** and **action items** widgets.

Chart rules:
- Series colours come from a validated colour-blind-safe palette (blue, orange, aqua in that fixed order), with separate shades for light and dark mode (`chartStyle.ts`).
- Axes show short rupee amounts (₹1.2L); tooltips show full amounts.
- Every chart has a visually hidden table with the same numbers, for screen readers.

## Performance

Each section runs a handful of aggregate queries, with no per-row loading. Finance months are grouped per day in SQL and bucketed into months in Python, which works on both SQLite and MySQL. The frontend caches the response for 60 seconds.

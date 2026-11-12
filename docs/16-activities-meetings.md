# 16 — Activities, Meetings & Action Items (T11)

One module for every organisation: the parish itself, the Council, committees, Anbiyam, Sabai, societies and associations.

**Who sees what.** Every list and record is limited to the organisations the user's roles cover:
- A role held for a unit also covers its sub-units.
- Parish-level records (no organisation) need a parish-wide grant.

## Activities

`activities` (`ACT-2026-0001`), `activity_participants`.

**Fields:**
- organisation, name, category (`SPIRITUAL`, `LITURGICAL`, `CHARITY`, `SOCIAL`, `CULTURAL`, `EDUCATIONAL`, `YOUTH`, `FAMILY`, `OTHER`)
- dates (start, optional end) and location
- responsible person: a member from the register or a typed name
- planned programme and planned budget
- actual outcome, actual cost and participant count
- participants: members or guests, with a role
- remarks and supporting documents

**Lifecycle:**

```
DRAFT ──submit──▶ IN_REVIEW ──(workflow)──▶ APPROVED ──record completion──▶ COMPLETED
  ▲                  │  └──return──▶ REWORK ──resubmit──▶ IN_REVIEW
  │                  └──reject──▶ REJECTED
  └──withdraw (submitter)
DRAFT / APPROVED ──cancel──▶ CANCELLED          DRAFT ──delete──▶ (soft-deleted)
```

- A record can be edited only while it is `DRAFT` or `REWORK`.
- Submitting starts the `ACTIVITY` workflow (T10). Its context includes the category and an amount (actual cost if known, otherwise the planned budget), so parishes can set up category-specific or amount-based approval chains.
- The default chain is: President of the organisation → Parish Secretary → Parish Priest. The status follows the workflow through the registered handler.
- Activities that already took place can be submitted with their outcome filled in. Otherwise, "Record completion" after approval adds the outcome and sets `COMPLETED`.

## Meetings & minutes

`meetings` (`MTG-2026-0001`), `meeting_agenda_items`, `meeting_attendance`, `meeting_minutes`, `discussion_points`, `resolutions`.

### Scheduling
- A meeting has a title, type (regular / special / general body / emergency), organisation, start and optional end, location, description, and an ordered agenda.
- **Times are the parish's local wall-clock time.** They are stored without a zone and compared with "now" in the parish time zone (Parish Settings).
- Scheduling, or moving the time, notifies the organisation's office bearers who have user accounts, plus the person who called the meeting (`meeting.scheduled`). They can turn this off with "Notify the office bearers".
- Cancelling notifies the same people (`meeting.cancelled`).
- A reminder goes out about 24 hours before (`meeting.reminder`, sent once).

### Attendance
- The list is pre-filled from the organisation's current members. For Anbiyam, it lists the families assigned to it.
- Each person is marked Present, Excused or Absent. Guests can be added.
- Saving attendance for a meeting whose start time has passed marks it `HELD`.

### Minutes
- Minutes have a summary, numbered discussion points (topic and discussion) and resolutions, each Passed, Deferred or Rejected.
- They can be written only once the meeting has started (`MEETING_NOT_HELD` before that).
- Submitting starts the `MEETING_MINUTES` workflow; the default chain is President → Parish Priest.
- While minutes are under review or approved, the minutes, attendance and meeting details are locked. Return for rework unlocks them.

### PDF
`GET /meetings/{id}/minutes.pdf` produces the Minutes of Meeting document:
- organisation, date, place and status
- attendance (present / excused / absent)
- agenda, summary, discussion and resolutions
- action items with the person responsible, due date and status
- signature lines

Minutes that are not yet approved carry a *DRAFT* watermark.

## Action items

`action_items` (`AI-2026-00001`), `action_item_updates`.

**What an item holds:**
- **Source:** a meeting, an activity, or nothing (created directly for an organisation).
- **Responsible:** a user account, so the person is notified and can update the item, or just a name for someone without a login.
- **Due date**, a status (`OPEN`, `IN_PROGRESS`, `DONE`, `CANCELLED`; "overdue" is computed from the due date) and progress in percent.
- **History of updates:** each note, progress change and status change.

**Who can create one:**

| Source | Needs |
|---|---|
| Meeting | `meeting.update` for the meeting's organisation |
| Activity | `activity.update` for the activity's organisation |
| Directly | `action_item.create` for the organisation |

**Who can see one:** the person responsible always can, even without any action-item permission. Coordinators with `action_item.view` see the items of their organisations.

**Who can update one:**
- The person responsible or a coordinator (`action_item.update`) can add progress, mark it done or cancel it.
- Only a coordinator can reopen a closed item or edit its title, owner or due date.

**Notifications:**
- `action_item.assigned` when an item is created for someone, or reassigned to them.
- `action_item.due` the day before it's due and on the due day.
- While it's overdue, the reminder repeats weekly.

## Calendar

`GET /calendar?start&end[&org_unit]` returns activities (all-day, multi-day ranges) and meetings visible to the user, for up to three months at a time. The screen:
- shows a month grid, with activities and meetings in two colours;
- switches to a list on phones;
- can filter by organisation.

## Attachments

`attachments` is a generic table (`entity_type`, `entity_id`). It's used for activities and meetings here, and will be reused by later modules.
- **Accepted files:** PDF, JPG/PNG, Word or Excel, at most 20 files per record. Each upload is checked with the shared upload validator (type and size limits).
- **Downloads** use the storage service's short-lived signed URLs.
- **Removing** a file hides it from the record; the stored object is kept.

## Background jobs

`app.tasks.maintenance.reminders` runs hourly through Celery beat. `ps-admin reminders` runs it by hand.

## API

| Endpoints | Permission (scoped to the record's organisation) |
|---|---|
| `GET /activities`, `/activities/{id}`, `/activities/{id}/attachments`, `/activities/categories` | `activity.view` |
| `POST /activities`, `PUT /activities/{id}` | `activity.create` / `activity.update` |
| `POST /activities/{id}/submit` | `activity.submit` |
| `POST /activities/{id}/complete`, `/cancel`, attachments upload/remove | `activity.update` |
| `DELETE /activities/{id}` (drafts) | `activity.delete` |
| `GET /activities/export?format=csv|xlsx|pdf` | `activity.export` |
| `GET /meetings`, `/meetings/{id}`, `/attendance`, `/minutes.pdf`, attachments | `meeting.view` |
| `POST /meetings`, `PUT /meetings/{id}`, `/cancel`, `PUT /attendance`, `PUT /minutes`, attachments | `meeting.create` / `meeting.update` |
| `POST /meetings/{id}/minutes/submit` | `meeting.submit` |
| `DELETE /meetings/{id}` (scheduled, no minutes) | `meeting.delete` |
| `GET /meetings/export` | `meeting.export` |
| `GET /action-items[?mine&status&overdue&org_unit&meeting&activity]`, `/action-items/{id}`, `/summary` | own items, or `action_item.view` |
| `POST /action-items`, `PATCH /action-items/{id}`, `POST /action-items/{id}/progress` | see above |
| `GET /calendar` | `activity.view` and/or `meeting.view` |
| `GET /org-units/mine?permission=…` | any signed-in user: the organisations they can act for (form pickers) |

## Screens

- **Activities:**
  - The list filters by organisation, status, category, dates and "recorded by me", and can be exported.
  - The form, where the organisation picker offers only units the user may record for.
  - The detail page has the actions bar, plan and outcome, participants, action items, supporting documents, and the approval timeline with the decision panel for the current reviewer.
- **Meetings & Minutes:**
  - Upcoming / past / all, with filters and export.
  - Scheduling dialog with agenda.
  - The detail page has tabs for overview, attendance, minutes (editor / view / PDF) and action items, plus the approval timeline and documents.
- **Action Items:** visible to everyone. Tabs for assigned to me / all (coordinators), with status and overdue filters, and a drawer with progress history and an update form.
- **Calendar.**
- **Dashboard:** upcoming meetings and my open action items.

## Role defaults changed in this release

- Parish Secretary gains `activity.create`, `update`, `submit` and `delete`.
- Parish President gains `activity.create`, `update` and `submit`, so parish-level activities can be recorded and submitted.
- Existing parishes keep their configured roles. Add these permissions in **Roles & Permissions** if wanted.
- The user picker (`/users/lookup`) is now also available to people who assign action items or review and approve records.

## Upgrading

```bash
ps-admin migrate-tenants
```

Tenant migration `0009` creates the eleven tables. Rebuild the containers so the worker's hourly reminder job is scheduled.

# 18 — Notices & News (T13)

Weekly notices, announcements, events, emergency notices, diocese circulars and parish news. Each notice is prepared, approved through the workflow engine, published on a schedule, and archived.

## Model

`notices` (`NTC-2026-0001`) lives in the tenant database (migration `20261113_0011_notices`). A notice has:

| Field | Notes |
|---|---|
| `category` | `WEEKLY`, `ANNOUNCEMENT`, `EVENT`, `EMERGENCY`, `DIOCESE`, `NEWS` |
| `title`, `body` | Required, in English |
| `title_local`, `body_local` | Optional Tamil text; readers switch between the two languages |
| `org_unit_id` | The preparing organisation; null means the parish |
| `audience` | `{"all": true}`, or `{"all": false, "org_units": [ids]}` |
| `is_important` | Highlighted on the board and sends the `notice.important` (email) notification. Always true for `EMERGENCY` |
| `is_public` | Shown on the public portal feed. Forced false for targeted notices |
| `publish_at`, `expires_at` | Parish wall-clock time. Expiry must be after publication |
| `status` | `DRAFT → IN_REVIEW → (REWORK) → APPROVED → PUBLISHED → ARCHIVED`, or `REJECTED` |

The API also returns a derived **state**:

- `DRAFT`, `IN_REVIEW`, `REWORK`, `REJECTED`, `ARCHIVED`
- `SCHEDULED`: approved, but `publish_at` is in the future
- `LIVE`: published and not expired
- `EXPIRED`: published and past `expires_at`

Notices also take attachments (generic attachments, entity type `NOTICE`).

## Approval

| Workflow | Applies to | Stages |
|---|---|---|
| `NOTICE_DEFAULT` | Every notice | Parish Secretary or President (optional, 48h SLA) → Parish Priest |
| `NOTICE_EMERGENCY` (priority 10) | Category `EMERGENCY` | Parish Priest only (2h SLA, escalates to the Parish Secretary) |

The preparer never approves their own stage. When the Secretary prepares a notice, the President takes the first stage.

Both workflows are seeded on migrate and can be edited in the workflow designer. Editing is allowed only in `DRAFT` or `REWORK`.

## Publication

- On final approval, a notice whose `publish_at` is empty or in the past goes live immediately. Otherwise it waits as `SCHEDULED`.
- The Celery beat job `app.tasks.maintenance.publish_notices` runs every 10 minutes and publishes notices that are due. You can also run it by hand with `ps-admin publish-notices`.
- **Publish now** (permission `notice.publish`) moves `publish_at` to now. **Archive** takes a notice off the board.
- When a notice is published, its audience is notified once:
  - `notice.important` for important or emergency notices (sent by email);
  - `notice.published` for all others.

## Audience

Readers see a notice on the board only if it is live and they are in its audience. A user belongs to an organisation if either:
- they hold a role scoped to it, or
- they are a current office bearer there.

For readers outside the audience, a targeted notice simply does not exist; opening its link returns 404. Drafts are visible only to people who manage notices.

## Permissions

| Permission | Allows |
|---|---|
| `notice.view` | The board, notice detail, the bulletin PDF |
| `notice.create`, `notice.update`, `notice.delete`, `notice.submit` | Preparing notices (scoped to an organisation where the role is scoped) |
| `notice.publish` | Publish now, archive, and the manage list |
| `notice.review` | Acting on approval stages |

The Parish Secretary now has `notice.publish` by default. **Existing parishes must tick it under Roles.**

## API (`/api/v1`)

| Method | Path | |
|---|---|---|
| GET | `/notices/board` | Live notices for me; filter by `category` and `q` |
| GET | `/notices/bulletin.pdf` | Printable bulletin of the live notices |
| GET / POST | `/notices` | Manage list with a `state` filter / create a notice |
| GET / PUT / DELETE | `/notices/{id}` | |
| POST | `/notices/{id}/submit`, `/publish`, `/archive` | |
| GET | `/notices/{id}/pdf` | One notice, printable |
| GET / POST / DELETE | `/notices/{id}/attachments[/{att}]` | |
| GET | `/public/notices` | **No sign-in.** Live public notices, for the future parish portal |

## UI

- **Content → Notices & News**: a board with category chips, search and *Print bulletin*. The *Manage* tab lists every notice with its state.
- **Notice form**: category, English and Tamil text, important flag, audience (everyone, or selected organisations), public toggle, publish and expiry times.
- **Notice detail**: an English/தமிழ் switch, the approval timeline, attachments, PDF, and Publish now / Archive.
- **Dashboard**: a *Latest notices* card, with important notices highlighted.

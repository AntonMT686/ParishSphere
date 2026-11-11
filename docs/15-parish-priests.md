# 15 — Parish Profile & Priests (T9)

## Parish profile

`parish_profile` (tenant DB) holds one row (`id = 1`), created by the `parish.profile` seeder from the master `parishes` record when a parish is provisioned.

| Group | Fields |
|---|---|
| Details | name, Tamil name, patron saint, established on, about |
| Address & contact | address lines, city, state, PIN, phone, email, website (`http(s)://…`) |
| Branding | logo (PNG/JPEG, ≤ 2 MB, content-sniffed), theme colour `#RRGGBB` |
| Regional | default language (`en`/`ta`), currency (ISO code), time zone, financial-year start month (1–12, default April) |

**Who can do what:**
- Every signed-in user can read the profile at `GET /parish/profile`.
- Changes need `settings.update`. It is granted parish-wide and audited as `parish.profile.update` with field-level changes.

**Sync to master.** On every change, the fields needed *before* sign-in are copied to the master database: name, address and contacts go to `parishes`, and display name, logo URL, colour, language, currency, time zone and FY month go to `tenant_settings`. The tenant cache is then invalidated. As a result:
- the sign-in page shows the parish name and logo straight away;
- the whole UI re-themes to the parish colour.

**Logo storage and serving:**
- The logo is stored through the storage service under `<parish>/branding/…`, and the previous file is deleted.
- It is served publicly by `GET /tenant/logo?v=<version>`, resolved by subdomain or `X-Parish-Code` and cached for one day.
- The version number changes on every upload, so caches never show a stale logo.

## Priests

| Table | Purpose |
|---|---|
| `priests` | Title (default "Rev. Fr."), name (English/Tamil), dates of birth and ordination, clergy type (`DIOCESAN` + home diocese, or `RELIGIOUS` + congregation), contacts, status (`ACTIVE`, `RETIRED`, `DECEASED`, `LEFT`), optional linked `user_id` |
| `priest_assignments` | Role (`PARISH_PRIEST`, `ASSISTANT_PRIEST`, `RESIDENT_PRIEST`, `DEACON`, `OTHER`), `appointed_on`, `relieved_on`, responsibilities, appointment letter no., relieving reason, link to the role grant it created |

Assignments are ended, never deleted. Together they form the parish's history of clergy.

### Handover-date semantics

`relieved_on` is the **handover date**: the first day the priest no longer serves.
- An assignment is current on day *d* when `appointed_on ≤ d < relieved_on`.
- The UI labels this column "Handed over on".

This makes the usual same-day handover representable: Fr. A hands over on 1 June, and Fr. B is appointed from 1 June. An inclusive end date could not express that without a one-day gap or overlap.

- `relieved_on` must be later than `appointed_on`, so a zero-length assignment is rejected.
- Relieving with a future date keeps the priest serving until the day before.

### Rules

- **Only active priests** can be appointed. A priest can't hold the same role twice at the same time (`ALREADY_ASSIGNED`).
- **One Parish Priest at a time.** Appointing a Parish Priest while another is current fails with `CURRENT_PARISH_PRIEST_EXISTS`, unless `relieve_current: true` is sent. In that case:
  - the predecessor is relieved with `relieved_on = new appointed_on`;
  - the reason is recorded as "Succeeded by …".
- **The role follows the assignment.** When a Parish Priest assignment has a linked active user account:
  - That account is granted the `PARISH_PRIEST` role, valid from `max(appointed_on, today)` to `relieved_on − 1`.
  - When the assignment ends, the grant ends: immediately for a past or today's handover, or on the day before a future handover.
  - Linking a different account moves the grant. Unlinking ends it.
  - A role the user already holds independently is never taken over or removed.
- **Linking an account** needs `user.assign_role` as well as `priest.update`. A user can be linked to only one priest (`USER_ALREADY_LINKED`), and you cannot link your own account.
- **Status change** to `RETIRED`, `DECEASED` or `LEFT` ends all current and future assignments today.

## API

| Method & path | Permission |
|---|---|
| `GET /parish/profile` | signed in |
| `PATCH /parish/profile` | `settings.update` |
| `POST /parish/profile/logo` (multipart `file`), `DELETE /parish/profile/logo` | `settings.update` |
| `GET /parish/clergy` (who serves today: names and roles) | signed in |
| `GET /tenant/logo` | public |
| `GET /priests?q=&status=&serving=&sort=` | `priest.view` |
| `POST /priests` | `priest.create` |
| `GET/PATCH /priests/{id}`, `POST /priests/{id}/status` | `priest.view` / `priest.update` |
| `POST /priests/{id}/user` (`user_id` or `null`) | `priest.update` + `user.assign_role` |
| `POST /priests/{id}/assignments`, `POST /priests/{id}/assignments/{aid}/relieve` | `priest.update` |

## Screens

- **Administration → Parish Settings** (`settings.view`; editable with `settings.update`):
  - parish details, address and contact
  - branding: logo upload/remove, colour picker
  - regional settings
- **Administration → Priests:**
  - The list has search, status and "serving now" filters.
  - The detail page has details, the linked user account, and the appointments table with Appoint and Relieve dialogs.
  - The Appoint dialog offers "Relieve the current Parish Priest (handover on …)" for Parish Priest appointments.
- **Dashboard:** the Parish Priest and the other serving clergy, for every user.
- **Sign-in page:** the parish logo.

## Upgrading an existing installation

Tenant migration `0007` creates the three tables:

```bash
ps-admin migrate-tenants
```

The profile row is created on first access from the master parish record.

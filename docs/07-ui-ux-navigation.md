# 07 — UI/UX Architecture & Navigation

## 1. Visual direction

Modern enterprise SaaS, calm and dignified (fits a church context) — not ornate.

| Token | Light | Dark | Use |
|---|---|---|---|
| `primary` | `#2F3E9E` (deep indigo) | `#8C9EFF` | Primary actions, active nav |
| `secondary` | `#B8860B` (liturgical gold) | `#E0B54A` | Highlights, festival accents |
| `success` | `#2E7D32` | `#66BB6A` | Approved |
| `warning` | `#ED6C02` | `#FFA726` | Pending / over budget |
| `error` | `#C62828` | `#EF5350` | Rejected |
| `info` | `#0277BD` | `#4FC3F7` | In review |
| `background.default` | `#F6F7FB` | `#0F1220` | App background |
| `background.paper` | `#FFFFFF` | `#171B2E` | Cards |
| `text.primary` | `#1B1F3B` | `#E8EAF6` | |

- Typography: **Inter** (Latin) + **Noto Sans Tamil**; scale 12/14/16/20/24/32; weights 400/500/600.
- Spacing: 4-px base (MUI `spacing(1)=8px`), card radius 12, subtle elevation (shadow 1–2), 1-px dividers.
- Icons: Material Symbols (rounded).
- Motion: 150–200 ms ease-out; skeletons for loading.

## 2. Design-system components (`frontend/src/design-system`)

`AppThemeProvider`, `PageHeader` (title, breadcrumbs, actions), `StatCard` (value, delta, icon, sparkline), `ChartCard`, `StatusBadge` (maps status → colour), `DataTable` (server pagination/sort/filter, column visibility, density, export, row actions, bulk actions), `FilterBar`, `SearchSelect` (async autocomplete), `FormField` wrappers (RHF + Zod), `FormStepper`, `ConfirmDialog`, `EmptyState`, `LoadingSkeleton`, `ApprovalTimeline`, `ActivityTimeline`, `AmountText` (currency formatting), `DateText`, `PermissionGate`, `IdleTimeoutDialog`.

## 3. Navigation structure — Admin workspace

```
Overview
  ├─ Dashboard (role-based)
  └─ Calendar
People
  ├─ Families
  ├─ Members
  └─ Registers (Marriage, Baptism, Communion, Confirmation, Custom)   [phase 2]
Organisations
  ├─ Parish Council (Peravai)
  ├─ Committees
  ├─ Anbiyam
  ├─ Sabai
  └─ Societies & Associations
  (menu generated from configured org unit types)
Activities
  ├─ Activities
  ├─ Meetings & Minutes
  └─ Action Items
Approvals
  ├─ My Approvals (badge count)
  └─ Submitted by Me
Finance
  ├─ Transactions
  ├─ Monthly Statements
  ├─ Accounts
  └─ Categories
Festivals & Events                                                    [phase 2]
Content
  ├─ Notices & News
  └─ Documents                                                        [phase 2]
Reports
Administration
  ├─ Users
  ├─ Roles & Permissions
  ├─ Workflows
  ├─ Organisation Types & Positions
  ├─ Priests
  ├─ Parish Profile & Settings
  └─ Audit Log
```

Platform console (`/platform`, super admin): Dioceses · Parishes · Plans & Subscriptions · Provisioning jobs · Platform audit.

## 4. Layouts

### Admin layout
```
┌──────────────────────────────────────────────────────────────────────┐
│ ☰  [Logo] St. Mary's Church   🔍 Search families, members…   🔔3  EN/த  👤 │
├──────────────┬───────────────────────────────────────────────────────┤
│ Overview     │ Home › Families                                        │
│  Dashboard   │ Families                               [+ Register]    │
│ People       │ ┌ Filters: Anbiyam ▾ Status ▾ Registered ▾  Search… ┐ │
│  Families  ● │ │ Code     Family     Head        Anbiyam  Members St│ │
│  Members     │ │ FAM00012 Arokiasamy John A.     St.Joseph   5   ●  │ │
│ Organisations│ │ …                                                   │ │
│ Activities   │ └─────────────────────────────── 1–25 of 1,240  ‹ › ┘ │
│ Approvals (4)│                                                        │
│ Finance      │                                                        │
│ …            │                                                        │
└──────────────┴───────────────────────────────────────────────────────┘
```
Sidebar collapses to icons (≥ md) or a drawer (mobile). Breadcrumbs on every page.

### Portal layout (phase 2)
Top bar with parish logo/name, large friendly cards (My Family, Notices, Events, Donate), bottom nav on mobile, warm palette variant (gold primary), larger type.

## 5. Sample: Parish Priest dashboard

```
┌ Good morning, Fr. Antony ───────────────────────── FY 2026-27 ▾ ┐
│ [Families 1,240 ▲12] [Members 4,812] [Anbiyam 24] [Societies 9] │
│ [Pending approvals 7 ▸] [Pending finance 3 ▸]                    │
├──────────────────────────────┬──────────────────────────────────┤
│ Income vs Expense (12 mo)    │ My Approvals                     │
│  ▇▆▇█▅▇ bar/line chart       │  • Youth Society – Career Camp   │
│                              │  • TXN-2026-000045 ₹62,000       │
├──────────────────────────────┤  • Weekly notice 16 Nov          │
│ Donations by purpose (donut) │ Upcoming (7 days)                │
│                              │  Tue Council meeting 6pm         │
├──────────────────────────────┴──────────────────────────────────┤
│ Recent activity timeline: approvals, new families, notices…     │
└─────────────────────────────────────────────────────────────────┘
```

Other dashboards:
- **President/Secretary:** pending reviews, minutes awaiting review, upcoming meetings, open/overdue action items, activity summary by org unit.
- **Treasurer:** income/expense month & YTD, category breakdown, pending finance approvals, period status timeline, budget vs actual.
- **Member preview:** notices, events, family card, Anbiyam info.

## 6. Key page patterns

- **List pages:** PageHeader + FilterBar + DataTable; filters encoded in URL query (non-sensitive), saved views later.
- **Detail pages:** header card (code, status badge, key facts, actions menu) + tabs (Overview, Members/Participants, Documents, Approval history, Audit).
- **Create flows:** `FormStepper` for families (Family → Address → Members → Anbiyam → Review), drafts saved server-side for long forms.
- **Workflowable records:** status banner ("Pending: Parish Secretary · since 2 days") + ApprovalTimeline + action bar (Approve / Return / Reject) for assignees.
- **Empty states** with a clear primary action; **skeletons** on load; **toasts** for success; inline field errors from backend `details`.

## 7. Responsiveness & accessibility

Breakpoints xs/sm/md/lg/xl; tables become card lists < sm; touch targets ≥ 44px; WCAG 2.1 AA contrast; full keyboard navigation; `aria-live` for toasts; language switch at runtime (en/ta).

## 8. Implemented frontend architecture (T6)

| Concern | Implementation |
|---|---|
| API types | Generated from the backend's OpenAPI: `cd backend && python scripts/export_openapi.py`, then `cd frontend && npm run gen:api` (writes `src/api/schema.d.ts`; aliases in `src/api/types.ts`). Regenerate whenever an API changes. |
| HTTP client | `src/api/client.ts` (axios): tenant header on localhost, bearer token held **in memory**, `X-CSRF-Token` copied from the `ps_csrf` cookie on unsafe requests, the error envelope mapped to `ApiError`. On `TOKEN_EXPIRED` it refreshes once and retries. Concurrent requests share one refresh, and refreshes across tabs are serialised with the Web Locks API, so a single-use refresh token is never replayed. |
| Session | `src/auth/authStore.ts` (zustand): page load restores the session through the refresh cookie (skipped when no session cookie exists). Login and refresh responses carry the user's roles and permissions. Sign-out is broadcast to other tabs (`BroadcastChannel`). The query cache is cleared on sign-out. |
| Idle timeout | `src/auth/IdleTimeoutDialog.tsx`: activity (mouse, keys, scroll, touch) is shared across tabs through `localStorage`. A warning with a countdown appears 2 minutes before the 30-minute limit. "Continue session" refreshes the session, which also extends the server's idle window. At the limit the user is signed out and sent to `/login?reason=timeout`. Access tokens are refreshed ahead of time only while the user is active. Nothing polls the API, because background calls would keep idle sessions alive. |
| Guards | `RequireAuth` redirects to login and remembers `from`; it also forces `/change-password` when `must_change_password` is set. `RequirePermission` shows a 403 page and `PermissionGate` hides controls. Navigation items declare their `permission`. All of this is UX only: the API enforces every permission. |
| Design system | `DataTable` (MUI X DataGrid with server-side paging and sorting), `FormTextField`/`FormSelect`/`FormSwitch` with `applyServerErrors` (backend field errors shown on the fields), `useFeedback()` (toasts and confirm dialogs), `ExportMenu` (authenticated XLSX/CSV/PDF downloads), `StatusBadge`, `StatCard`, `PageHeader`, `EmptyState`. |
| Screens | Login, forgot password, reset/invite password, forced password change. Profile (details, password, signed-in devices, notification preferences). Notification bell and notifications page. Users (list, filters, create or invite, drawer with status actions and role history), roles (cards, permission editor), audit log (filters, change viewer, export). |
| Tests | Vitest + Testing Library + MSW (`src/test/server.ts`): refresh single-flight and retry, CSRF header, session-ended handling, idle warning and expiry, guards and redirects, login, forced password change, permission-filtered navigation, server-paged users table. |

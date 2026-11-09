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

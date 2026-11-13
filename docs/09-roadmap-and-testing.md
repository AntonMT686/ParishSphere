# 09 — Implementation Roadmap & Testing Strategy

## 1. Phases

| Phase | Goal | Output |
|---|---|---|
| 1. Requirement analysis | Scope, entities, roles, workflows, gaps | `01-product-requirements.md` |
| 2. Solution architecture | System, tenancy, security, API | `02`, `03`, `06`, `08` |
| 3. UI/UX | Navigation, layouts, design system | `07` + design-system code |
| 4. Database design | Master & parish schemas, ERDs, migrations | `04` + Alembic |
| 5. Core development | Tasks T1–T15 below | Code + tests |
| 6. Testing | Unit, API, integration, isolation, security, perf, UAT | CI + reports |
| 7. Deployment | Docker, environments, HTTPS, backups, monitoring | `10` + infra |

## 2. Development tasks (dependency order)

| # | Task | Depends on | Acceptance |
|---|---|---|---|
| T0 | Architecture docs | — | Docs reviewed |
| T1 | Scaffold: backend, frontend, docker-compose, lint, CI | T0 | `make up` serves health + SPA; CI green |
| T2 | Master DB + tenancy core + provisioning/migration CLI + diocese/parish APIs | T1 | Two parishes provisioned; requests routed by subdomain/header |
| T3 | Auth & sessions (login, refresh rotation, idle timeout, lockout, reset) | T2 | Security tests pass |
| T4 | RBAC & user management (17 roles, scoped assignments) | T3 | Scope tests pass |
| T5 | Common services: audit, sequences, ULID, soft delete, pagination, exports, storage, notifications | T2 | Audit rows on CRUD |
| T6 | Frontend shell + design system + login + idle modal + guards | T3, T4 | Login → dashboard shell |
| T7 | Configurable org units | T4, T5 | Council/Committee/Anbiyam/Sabai/Society created as data |
| T8 | Families & members | T7 | Register/transfer/merge/split/deceased with history |
| T9 | Parish profile & priests | T5 | Assignment history |
| T10 | Workflow engine + designer + inbox | T4, T7 | Workflow test matrix passes |
| T11 | Activities & meetings (MOM, action items) | T10 | 3-stage approval demo |
| T12 | Finance + monthly statements | T10 | Statement PDF/XLSX, lock, revision |
| T13 | Notices & news | T10 | Publish flow |
| T14 | Role dashboards | T8–T13 | Charts render with seed data |
| T15 | Global search, MVP reports, audit viewer | T8–T13 | Exports work |
| T16 | Hardening, e2e, prod compose, demo seed, install guide | all | Demo-ready MVP |

**Phase 2:** T17 Member portal · T18 Donations (Razorpay, webhooks, receipts) · T19 Festivals & budgets · T20 Documents/versions/digitisation (+ OCR) · T21 Configurable registers & custom fields (marriage, sacraments, Niyanasthanam) · T22 Excel import & bulk registration · T23 Diocese analytics · T24 Backup/restore tooling · T25 SMS/WhatsApp.

## 3. MVP for the first parish demo

Login on the parish subdomain → Priest dashboard with real numbers → register a family with members in an Anbiyam → Youth Society secretary records an activity → President → Parish Secretary → Priest approve (timeline visible) → Society treasurer enters an expense → Parish treasurer reviews → Priest approves → month closed, statement PDF released → weekly notice approved and published → audit log shows all of it.

## 4. Testing strategy

| Level | Tooling | Focus |
|---|---|---|
| Unit | pytest | services, workflow engine, finance calculations, permission resolution, ID/sequence generation |
| API | pytest + FastAPI TestClient | contracts, validation, error envelope, pagination, auth flows |
| Integration | pytest + MySQL 8 service container (CI) / SQLite (fast local) | migrations, provisioning, multi-tenant routing |
| Tenant isolation | dedicated suite | token from A on B host → 403; IDs from A on B → 404; no shared engines |
| Workflow | parametrised suite | sequential, parallel ALL/ANY, optional skip, reject, return/resubmit, delegate, escalate, definition versioning |
| Security | pytest + OWASP ZAP baseline (CI nightly) | lockout, refresh reuse, idle timeout, CSRF, headers, upload validation |
| Frontend | Vitest + React Testing Library | components, hooks, guards, idle timer |
| E2E | Playwright (`frontend/e2e`, `make e2e`, CI job `e2e`) | MVP demo journey on the `seed-demo` parish: 10 serial steps, ~30 s |
| Performance | Locust | targets below with 50k members / 200k transactions seed |
| UAT | Scripted scenarios with pilot parish | sign-off checklist |

Coverage goal: ≥ 85 % on services/engine; every bug fix adds a regression test.

**T16 hardening results** (SQLite, 3,000 families / 12,000 members, single process): family list 0.05 s, family search 0.05 s (was 6.4 s – correlated member subquery replaced), member list/search 0.02 s, global search 0.02–0.03 s, dashboard 0.07 s, family register report 0.47 s (was 4.5 s – members batch-loaded), Excel export of 3,000 rows 0.2 s (was 9 s – quadratic cell scan removed). Production-mode checks: API docs off, `Secure`/`HttpOnly`/`SameSite=strict` cookies, JSON logs, account lockout after 5 failures, append-only audit log enforced in the application.

## 5. Performance targets

| Operation | Target (p95) |
|---|---|
| Dashboard load (API) | < 800 ms (cached < 150 ms); page interactive < 1.5 s |
| List/search APIs | < 300 ms at 50k members |
| Global search | < 500 ms |
| Single record CRUD | < 200 ms |
| Monthly statement generation | < 10 s (async job) |
| Export ≤ 10k rows | < 15 s (async above) |
| Document upload 10 MB | < 3 s to storage; processing async |
| Document download URL | < 200 ms |

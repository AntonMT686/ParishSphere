# ParishSphere — Documentation Index

> **One Digital Platform. Every Parish. Every Family. Every Ministry.**

| # | Document | Contents |
|---|----------|----------|
| 01 | [Product Requirements](01-product-requirements.md) | Vision, domains, PRD/BRS/FRS summary, roles & permission matrix, feature classification, missing requirements & open questions |
| 02 | [Solution Architecture](02-solution-architecture.md) | System context, components, backend/frontend layering, module dependencies, background jobs, storage, notifications |
| 03 | [Multi-Tenant Architecture](03-multi-tenant-architecture.md) | Database-per-parish design, tenant resolution, connection lifecycle, provisioning, migrations, diocese view, backup & recovery |
| 04 | [Database Design](04-database-design.md) | Master & parish schemas, conventions, Mermaid ER diagrams |
| 05 | [Workflow Engine](05-workflow-engine.md) | Configurable approval engine, state machines, example workflows, implementation & API (T10) |
| 06 | [Security](06-security.md) | AuthN/AuthZ, sessions & idle timeout, HTTPS, uploads, audit, OWASP controls |
| 07 | [UI/UX & Navigation](07-ui-ux-navigation.md) | Design system, navigation tree, layouts, sample dashboard & page wireframes |
| 08 | [API Standards](08-api-standards.md) | REST conventions, errors, pagination, filtering, versioning |
| 09 | [Roadmap & Testing](09-roadmap-and-testing.md) | Phases, task breakdown, MVP, test strategy, performance targets |
| 10 | [Deployment](10-deployment.md) | Docker topology, environments, HTTPS, logging, monitoring, migration strategy |
| 11 | [Role & Permission Matrix](11-permission-matrix.md) | Generated default grants for the 15 parish roles |
| 12 | [Platform Services](12-platform-services.md) | Developer guide: codes, audit, storage, exports, notifications |
| 13 | [Organisations](13-organisations.md) | Configurable council/committees/Anbiyam/Sabai/societies, office bearers → roles |
| 14 | [Families & Members](14-families-members.md) | Parish register, life events with history, duplicates, scoping, memberships |
| 15 | [Parish Profile & Priests](15-parish-priests.md) | Parish settings & branding, priests, assignment history with handover dates, role sync |
| 16 | [Activities, Meetings & Action Items](16-activities-meetings.md) | Activities with approval, meetings, attendance, minutes & PDF, action items, calendar, reminders |
| 17 | [Finance & Monthly Statements](17-finance.md) | Accounts, categories, one ledger with approval, corrections, receipts, month close → approve → release → revise |
| 18 | [Notices & News](18-notices.md) | Prepare → approve → scheduled publish → archive, audiences, emergency route, bulletin PDF, public feed |
| 19 | [Role Dashboards](19-dashboards.md) | Permission-driven dashboard sections, scoped figures, charts, member view |
| 20 | [Search, Reports & Audit](20-search-reports-audit.md) | Scoped global search, 21 MVP reports with CSV/Excel/PDF export, audit viewer filters |
| 21 | [Installation & Operations](21-installation.md) | Laptop demo, demo users & story, server install (Docker, TLS, first parish), upgrades, backups/restore, security checklist, troubleshooting, e2e |

Living documents: update them in the same PR as the code that changes the behaviour they describe.

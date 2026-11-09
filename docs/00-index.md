# ParishSphere — Documentation Index

> **One Digital Platform. Every Parish. Every Family. Every Ministry.**

| # | Document | Contents |
|---|----------|----------|
| 01 | [Product Requirements](01-product-requirements.md) | Vision, domains, PRD/BRS/FRS summary, roles & permission matrix, feature classification, missing requirements & open questions |
| 02 | [Solution Architecture](02-solution-architecture.md) | System context, components, backend/frontend layering, module dependencies, background jobs, storage, notifications |
| 03 | [Multi-Tenant Architecture](03-multi-tenant-architecture.md) | Database-per-parish design, tenant resolution, connection lifecycle, provisioning, migrations, diocese view, backup & recovery |
| 04 | [Database Design](04-database-design.md) | Master & parish schemas, conventions, Mermaid ER diagrams |
| 05 | [Workflow Engine](05-workflow-engine.md) | Configurable approval engine, state machines, example workflows |
| 06 | [Security](06-security.md) | AuthN/AuthZ, sessions & idle timeout, HTTPS, uploads, audit, OWASP controls |
| 07 | [UI/UX & Navigation](07-ui-ux-navigation.md) | Design system, navigation tree, layouts, sample dashboard & page wireframes |
| 08 | [API Standards](08-api-standards.md) | REST conventions, errors, pagination, filtering, versioning |
| 09 | [Roadmap & Testing](09-roadmap-and-testing.md) | Phases, task breakdown, MVP, test strategy, performance targets |
| 10 | [Deployment](10-deployment.md) | Docker topology, environments, HTTPS, logging, monitoring, migration strategy |
| 11 | [Role & Permission Matrix](11-permission-matrix.md) | Generated default grants for the 15 parish roles |

Living documents: update them in the same PR as the code that changes the behaviour they describe.

# ParishSphere

**One Digital Platform. Every Parish. Every Family. Every Ministry.**

Multi-tenant parish management SaaS: families & members, configurable parish organisations (Council, Committees, Anbiyam, Sabai, Societies), activities & meetings, a configurable approval workflow engine, finance with monthly statements, notices, and full audit — with a separate database per parish.

- Product scope: [`ParishSphere_Project_context.md`](ParishSphere_Project_context.md)
- Architecture & design: [`docs/`](docs/00-index.md)

| Layer | Stack |
|---|---|
| Frontend | React 18, TypeScript, Vite, MUI 6, TanStack Query, React Router |
| Backend | Python, FastAPI, SQLAlchemy 2, Alembic, Celery |
| Data | MySQL 8 (master + one DB per parish), Redis, S3-compatible storage |
| Ops | Docker, Nginx |

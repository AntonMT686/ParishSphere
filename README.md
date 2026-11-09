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

## Quick start (development)

```bash
make up          # MySQL, Redis, MinIO, MailHog, API, worker, Vite, Nginx
make seed-demo   # super admin + diocese CHN + parish STMARYS with user admin / ChangeMe-Now1
```

Open http://stmarys.parishsphere.localhost (or http://localhost:5173 and enter parish code `STMARYS`). API docs: http://localhost:8000/api/v1/docs.

Without Docker (SQLite, for quick backend work):

```bash
make backend-install
cd backend && PS_MASTER_DATABASE_URL=sqlite:///data/master.db PS_TENANT_DB_DRIVER=sqlite \
  .venv/bin/ps-admin migrate-master
```

| Command | Purpose |
|---|---|
| `ps-admin migrate-master` | Upgrade the master database |
| `ps-admin provision-parish --diocese CHN --code X --name "…"` | Register + create + migrate + seed a parish DB (idempotent) |
| `ps-admin migrate-tenants --parallel 8` | Upgrade every parish database |
| `make test` / `make lint` | Backend + frontend tests / linters |

## Frontend development

```bash
cd frontend && npm install
VITE_DEFAULT_PARISH_CODE=STMARYS npm run dev     # http://localhost:5173 (proxies /api to :8000)
npm test && npm run lint && npm run typecheck
```

After changing backend APIs, regenerate the TypeScript types:

```bash
cd backend && .venv/bin/python scripts/export_openapi.py && cd ../frontend && npm run gen:api
```

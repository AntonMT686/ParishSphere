# 10 — Deployment Architecture

## 1. Containers

| Service | Image | Notes |
|---|---|---|
| `nginx` | nginx:1.27-alpine | TLS termination, HTTP→HTTPS, gzip, security headers, SPA static files, `/api` proxy, rate limits |
| `api` | `parishsphere/backend` | `uvicorn app.main:app` (gunicorn + uvicorn workers in prod), N replicas |
| `worker` | same image | `celery -A app.worker worker -Q notifications,documents,workflow,maintenance` |
| `beat` | same image | `celery -A app.worker beat` (single instance) |
| `mysql` | mysql:8.4 | master + parish DBs (prod: managed MySQL / dedicated hosts) |
| `redis` | redis:7-alpine | cache, broker, rate limits |
| `minio` | minio/minio | dev/UAT object storage (prod: S3-compatible service) |
| `frontend` (dev only) | node:22 | Vite dev server with HMR |

## 2. Environments

| Env | Purpose | Notes |
|---|---|---|
| development | local `docker compose -f infra/docker-compose.dev.yml up` | HTTP, `*.localhost` subdomains, shared DB creds, MailHog for email |
| test/CI | GitHub Actions | MySQL & Redis service containers |
| UAT | pilot parish validation | prod-like, anonymised data, TLS |
| production | live | TLS, per-tenant DB users, managed backups, monitoring |

Configuration exclusively via environment variables (`PS_*`), documented in `backend/.env.example`. Secrets from the platform secret store.

## 3. HTTPS

- Wildcard certificate `*.parishsphere.app` (Let's Encrypt DNS-01 via certbot/acme.sh) + apex.
- `server { listen 80; return 301 https://$host$request_uri; }`
- HSTS, TLS 1.2/1.3 only, OCSP stapling.
- Custom parish domains (future): per-domain certificates via ACME HTTP-01.

## 4. Deployment flow

1. CI builds & tests → images tagged with git SHA.
2. `ps-admin migrate-master` (expand-only migration).
3. Rolling deploy of `api`/`worker`.
4. `ps-admin migrate-tenants --parallel 8` (batched; failures reported).
5. Smoke tests; contract migrations in a later release.

## 5. Logging & monitoring

- JSON logs (structlog) with `trace_id`, `tenant`, `user`, `path`, `status`, `duration_ms` → Loki/ELK.
- `/api/v1/health/live` (process), `/api/v1/health/ready` (master DB + Redis).
- Metrics (phase 2): Prometheus `/metrics` (request latency, DB pool usage per tenant, Celery queue depth); Grafana dashboards; alerting on error rate, latency, failed migrations, backup failures.
- Error tracking: Sentry-compatible DSN optional.

## 6. Backup & restore

See [03 §9](03-multi-tenant-architecture.md#9-backup--recovery). Backups are scheduled by Celery beat (`maintenance` queue) or host cron; restore drills monthly.

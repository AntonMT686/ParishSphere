# 21 — Installation & Operations Guide (T16)

How to run ParishSphere:
- on a **laptop for a demo**;
- on **one server for UAT or production**;
- and how to keep a server running (upgrades, backups, restore).

## 1. Quick demo on a laptop

### With Docker (Windows, macOS or Linux)

Requires Docker Desktop (Windows: WSL 2 backend) with 4 GB RAM available.

```bash
git clone <your repository URL> ParishSphere && cd ParishSphere
make up            # or: docker compose -f infra/docker-compose.dev.yml up -d --build
make seed-demo     # super admin + demo parish "St. Mary's Church" (≈ 15 s)
```

Open **http://stmarys.parishsphere.localhost**. On Windows, if `*.localhost` does not resolve, open http://localhost:5173 and enter parish code `STMARYS`.

### Without Docker (Python 3.12+ and Node 22)

```bash
make backend-install && make frontend-install
cd backend
export PS_MASTER_DATABASE_URL=sqlite:///data/master.db PS_TENANT_DB_DRIVER=sqlite
.venv/bin/ps-admin migrate-master && .venv/bin/ps-admin seed-demo
.venv/bin/uvicorn app.main:app --port 8000 &
cd ../frontend && VITE_DEFAULT_PARISH_CODE=STMARYS npm run dev   # http://localhost:5173
```

### Demo users

Every demo user's password is `ChangeMe-Now1`, or the value given with `--password`.

| User | Role | Shows |
|---|---|---|
| `frjoseph` | Parish Priest | Full dashboard. Waiting for him: a ₹62,000 roof repair, last month's statement, youth meeting minutes |
| `raj` | Parish President | Review queues, committee activity |
| `mary` | Parish Secretary | Registers, notices, meetings; a Youth Society activity waits for her |
| `peter` | Parish Treasurer | Accounts, four months of entries, released statements |
| `anitha` | Anbiyam Leader | Only St. Joseph Anbiyam's families |
| `jerome` | Youth Society President | Reviews the society's activities |
| `kevin` | Youth Society Secretary | Records society activities and meetings |
| `thomas` | Parishioner | Own family, donations, notices, events |
| `admin` | Parish Administrator | Users, roles, workflows, settings, audit log |

**The demo story (about 10 minutes):**
1. Sign in as `frjoseph` and look at the dashboard.
2. Approve the roof repair, then approve and release last month's statement and download the PDF.
3. As `kevin`, record an activity. It goes to `jerome`, then `mary`, then `frjoseph`, with the timeline on the activity.
4. As `mary`, prepare a weekly notice. It goes to `raj`, then `frjoseph`.
5. As `thomas`, see the notice on the dashboard.
6. As `admin`, open *Audit log* to see every step.

`ps-admin seed-demo` refuses to touch a parish that already has families. Never run it on a live parish.

## 2. Server installation (UAT / production)

### 2.1 What you need

| Item | Minimum (1–20 parishes) | Notes |
|---|---|---|
| Server | 2 vCPU, 4 GB RAM, 40 GB SSD | Ubuntu 22.04/24.04 LTS or any Docker host |
| Software | Docker Engine 24+ with the Compose plugin, `git`, `make` | |
| DNS | `A` records for `example.org` **and** `*.example.org` → server IP | Each parish is `<subdomain>.example.org` |
| TLS certificate | Wildcard `*.example.org` + `example.org` | Let's Encrypt DNS-01 (below) |
| SMTP account | Any provider | Password resets, approvals, notices |
| Firewall | Allow 80 and 443 only | MySQL and Redis are never published |

### 2.2 Get the code and configure

```bash
sudo mkdir -p /opt && cd /opt && sudo git clone <your repository URL> parishsphere && cd parishsphere
sudo cp infra/prod.env.example infra/.env && sudo chmod 600 infra/.env
sudo nano infra/.env      # replace every CHANGE-ME (domain, passwords, secrets, SMTP)
```

Generate the secrets the file asks for:

```bash
openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-48          # PS_SECRET_KEY, database passwords
python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # PS_SECRET_ENCRYPTION_KEY
```

The API refuses to start in production with a weak `PS_SECRET_KEY`, a missing `PS_SECRET_ENCRYPTION_KEY`, or shared tenant credentials. **Keep `PS_SECRET_ENCRYPTION_KEY` safe:** it encrypts the per-parish database passwords, and they cannot be recovered without it.

### 2.3 TLS certificate (wildcard)

The wildcard certificate needs a DNS challenge. Example with certbot and your DNS provider's plugin (Cloudflare shown):

```bash
sudo apt install certbot python3-certbot-dns-cloudflare
sudo certbot certonly --dns-cloudflare --dns-cloudflare-credentials ~/.cloudflare.ini \
  -d example.org -d '*.example.org'
sudo mkdir -p infra/certs
sudo cp /etc/letsencrypt/live/example.org/{fullchain.pem,privkey.pem} infra/certs/
```

For renewal, add a deploy hook that copies the two files again and runs `docker compose -f infra/docker-compose.prod.yml exec web nginx -s reload`.

Without a certificate yet (trial install on a private network), set `PS_NGINX_TEMPLATE=http` in `infra/.env`. Behind a load balancer that terminates TLS, use `http` and set `PS_COOKIE_SECURE=true`.

### 2.4 Start

```bash
make prod-up      # = docker compose -f infra/docker-compose.prod.yml up -d --build
docker compose -f infra/docker-compose.prod.yml ps
```

| Service | Role |
|---|---|
| `mysql`, `redis` | Data and queue (volumes `mysql-data`, `redis-data`) |
| `migrate` | Runs on every start: upgrades the master database and every parish database, then exits |
| `api` | FastAPI, `WEB_CONCURRENCY` worker processes, health-checked on `/api/v1/health/ready` |
| `worker` | Background jobs: notifications, PDFs, workflow |
| `beat` | Scheduler (one instance): SLA escalations, meeting/action-item reminders, notice publishing |
| `web` | nginx: TLS, security headers, rate limits on sign-in, the built frontend, `/api` proxy |

Check: `curl -s https://example.org/api/v1/health/ready` should return `{"status":"ok",…}`.

### 2.5 First parish

```bash
P="docker compose -f infra/docker-compose.prod.yml exec api ps-admin"
$P create-superadmin --email you@example.org --name "Platform Admin"          # prompts for a password
$P create-diocese --code CHN --name "Archdiocese of Madras-Mylapore"
$P provision-parish --diocese CHN --code STMARYS --name "St. Mary's Church" \
   --subdomain stmarys --admin-username admin --admin-email office@stmarys.example.org
```

The parish administrator receives a link by email to set their password. They then sign in at `https://stmarys.example.org` and, in order:
1. complete the **Parish profile**;
2. add **Priests** (the Parish Priest assignment grants the Parish Priest role);
3. create **organisations** and appoint office bearers (posts grant roles);
4. create **users**;
5. review **Workflows**.

For a UAT or sales demo on the server (never on a live parish): `make prod-seed-demo`.

## 3. Operations

### Upgrades

```bash
cd /opt/parishsphere && make backup && git pull
make prod-up                     # rebuilds images; `migrate` upgrades every parish before the API starts
docker compose -f infra/docker-compose.prod.yml logs migrate     # check: every parish reports "ok"
```

Database migrations are expand-only, so the previous API version keeps working while parishes are upgraded.

### Backups

`make backup` (`scripts/backup.sh`) writes `backups/<timestamp>/`, keeping the last 14:
- `ps_master.sql.gz` and one `ps_t_<parish>.sql.gz` per parish;
- `files.tar.gz` with the uploaded documents.

Schedule it nightly and copy the folder off the server:

```cron
30 1 * * *  cd /opt/parishsphere && scripts/backup.sh >> /var/log/parishsphere-backup.log 2>&1
```

**Restore one parish** (e.g. `stmarys`) into the running stack:

```bash
gunzip -c backups/<timestamp>/ps_t_stmarys.sql.gz | \
  docker compose -f infra/docker-compose.prod.yml exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" ps_t_stmarys'
```

Practise a full restore on a spare machine every month.

### Monitoring and logs

- `make prod-logs` streams JSON logs. Each request line carries `trace_id`, `tenant`, `user`, `path`, `status` and `duration_ms`. Error responses carry the same `trace_id`, so a user's screenshot leads to the log line.
- Alert on `/api/v1/health/ready` ≠ 200, on a failing `migrate` container, and on failed backups.
- The audit log (Administration → Audit log, or the *User activity* report) shows who did what in each parish.

### Security checklist

- [ ] `infra/.env` is `chmod 600`, kept off git, with real secrets; `PS_ENV=production`.
- [ ] Only ports 80 and 443 are open; SSH uses keys.
- [ ] HTTPS with a valid wildcard certificate. HSTS is sent once HTTPS works: do not switch back to HTTP.
- [ ] API docs are off in production (`/api/v1/docs` → 404). Turn them on only for UAT with `PS_EXPOSE_DOCS=true`.
- [ ] SMTP works: test with "Forgot password".
- [ ] Nightly backups are copied off the server, and a restore has been tried.
- [ ] The platform super admin and the parish administrators have strong passwords.
- [ ] OS and Docker images are kept updated (`git pull && make prod-up` monthly).

Built-in protections:
- passwords hashed with Argon2;
- account lockout after repeated failures, plus nginx rate limits on sign-in;
- 30-minute idle timeout and 12-hour maximum session;
- `HttpOnly` / `Secure` / `SameSite=strict` cookies and CSRF tokens;
- per-parish databases with their own credentials;
- 404 for records outside the user's scope;
- upload type checks;
- CSV/Excel formula-injection guards;
- an append-only audit log (the application refuses to change or delete audit rows).

## 4. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pull access denied` for an image | Old checkout; `git pull` (MinIO was replaced by a files volume) |
| Docker Desktop "500 Internal Server Error" (Windows) | Restart Docker Desktop; if it persists, `wsl --shutdown` in PowerShell and start Docker Desktop again |
| `migrate` exits with an error | `docker compose … logs migrate`; usually the database password in `.env` does not match the one MySQL was first created with |
| API restarts with "PS_SECRET_KEY must be set…" | Production settings check: fill in the secrets in `infra/.env` |
| Parish page shows "Parish not found" | The subdomain is not registered, or DNS for `*.example.org` is missing |
| Emails not arriving | Check the `PS_SMTP_*` settings; without `PS_SMTP_HOST`, emails are only logged |
| Login "Too many attempts" | Lockout after repeated failures: wait 15 minutes, or an administrator resets the password |

## 5. Testing the installation

- The end-to-end suite, `scripts/e2e.sh` (or `make e2e`), runs the full MVP journey on a throwaway SQLite stack in about 30 s. It covers:
  - the dashboard;
  - family registration;
  - activity approval through three stages;
  - finance approval;
  - month close and statement release;
  - notice publishing;
  - the parishioner view;
  - search and report export;
  - the audit log;
  - sign-out.
- Against a running stack: `cd frontend && E2E_BASE_URL=https://stmarys.example.org npm run e2e`. Only run this on a demo parish, because the suite changes data.

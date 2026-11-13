COMPOSE = docker compose -f infra/docker-compose.dev.yml
BACKEND = cd backend &&
PY = .venv/bin/python

PROD = docker compose -f infra/docker-compose.prod.yml

.PHONY: up down logs seed-demo backend-install backend-test backend-lint frontend-install frontend-test frontend-lint test lint e2e prod-up prod-down prod-logs prod-seed-demo backup

up:            ## Start the full development stack
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api worker

seed-demo:     ## Super admin + demo parish STMARYS with staff, families, finance, activities (dev stack)
	$(COMPOSE) exec api ps-admin create-superadmin --email admin@parishsphere.org --name "Platform Admin" --password "ChangeMe-Now1" || true
	$(COMPOSE) exec api ps-admin seed-demo

backend-install:
	$(BACKEND) python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pip install --no-deps -e .

backend-test:
	$(BACKEND) $(PY) -m pytest

backend-lint:
	$(BACKEND) .venv/bin/ruff check . && .venv/bin/ruff format --check .

frontend-install:
	cd frontend && npm ci

frontend-test:
	cd frontend && npm test

frontend-lint:
	cd frontend && npm run lint && npm run typecheck

test: backend-test frontend-test
lint: backend-lint frontend-lint

e2e:           ## Playwright MVP journey on a throwaway SQLite stack (needs backend-install + frontend-install)
	scripts/e2e.sh

prod-up:       ## Build and start the production stack (infra/.env required)
	$(PROD) up -d --build

prod-down:
	$(PROD) down

prod-logs:
	$(PROD) logs -f --tail=100 api worker beat web

prod-seed-demo: ## Demo parish on the production stack (for UAT / sales demos only)
	$(PROD) exec api ps-admin seed-demo

backup:        ## Dump every database (master + parishes) to backups/ (production stack)
	scripts/backup.sh

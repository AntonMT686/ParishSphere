COMPOSE = docker compose -f infra/docker-compose.dev.yml
BACKEND = cd backend &&
PY = .venv/bin/python

.PHONY: up down logs seed-demo backend-install backend-test backend-lint frontend-install frontend-test frontend-lint test lint

up:            ## Start the full development stack
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api worker

seed-demo:     ## Create a super admin, a diocese and the demo parish STMARYS (dev stack)
	$(COMPOSE) exec api ps-admin create-superadmin --email admin@parishsphere.org --name "Platform Admin" --password "ChangeMe-Now1"
	$(COMPOSE) exec api ps-admin create-diocese --code CHN --name "Archdiocese of Madras-Mylapore"
	$(COMPOSE) exec api ps-admin provision-parish --diocese CHN --code STMARYS --name "St. Mary's Church"

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

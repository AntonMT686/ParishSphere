#!/usr/bin/env bash
# End-to-end run on a throwaway SQLite stack:
#   fresh databases → ps-admin seed-demo → API (:8000) + built frontend (:5173) → Playwright.
# Usage: scripts/e2e.sh [playwright args…]      e.g. scripts/e2e.sh --headed
# Needs: backend/.venv (make backend-install), frontend/node_modules (npm ci), and a Playwright
# Chromium (npx playwright install chromium, or PW_CHROMIUM_PATH=/path/to/chromium).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ps-e2e.XXXXXX")"
API_PORT="${E2E_API_PORT:-8000}"
WEB_PORT="${E2E_WEB_PORT:-5173}"
export PS_ENV=test PS_MASTER_DATABASE_URL="sqlite:///$WORK/master.db" PS_TENANT_DB_DRIVER=sqlite \
  PS_SQLITE_DATA_DIR="$WORK" PS_STORAGE_LOCAL_DIR="$WORK/files" PS_LOG_LEVEL=WARNING \
  PS_BASE_DOMAIN=parishsphere.localhost PS_REDIS_URL=
export E2E_BASE_URL="${E2E_BASE_URL:-http://stmarys.parishsphere.localhost:$WEB_PORT}"

cleanup() { kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true; rm -rf "$WORK"; }
trap cleanup EXIT

cd "$ROOT/backend"
.venv/bin/ps-admin migrate-master >/dev/null
.venv/bin/ps-admin seed-demo
.venv/bin/uvicorn app.main:app --port "$API_PORT" >"$WORK/api.log" 2>&1 &
API_PID=$!

cd "$ROOT/frontend"
VITE_API_PROXY="http://localhost:$API_PORT" npx vite build >/dev/null
VITE_API_PROXY="http://localhost:$API_PORT" npx vite preview --port "$WEB_PORT" --strictPort >"$WORK/web.log" 2>&1 &
WEB_PID=$!
for _ in $(seq 1 60); do
  curl -sf "http://localhost:$API_PORT/api/v1/health/live" >/dev/null && curl -sf "http://localhost:$WEB_PORT" >/dev/null && break
  sleep 1
done
npx playwright test "$@" || { echo "--- API log (last 40 lines)"; tail -40 "$WORK/api.log"; exit 1; }

#!/usr/bin/env bash
# Check a handover ZIP the way Rimsha will use it: unzip into an empty folder, copy
# .env.example to .env, install, migrate a fresh database, run every test and the web build.
#
#   scripts/verify_zip.sh ../reel2play.zip
#
# Needs a local PostgreSQL reachable as PG_ADMIN_URL (default: the postgres user on 127.0.0.1).
set -euo pipefail

ZIP="$(realpath "$1")"
PG="${PG_ADMIN_URL:-postgresql://postgres@127.0.0.1:5432}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== unzip into $WORK"
unzip -q "$ZIP" -d "$WORK"
cd "$WORK/reel2play"

echo "== no secrets inside"
if find . -name ".env" -o -name ".env.*" ! -name ".env.example" | grep -q .; then
  echo "found an .env file in the ZIP" >&2
  exit 1
fi
cp .env.example .env

for db in r2p_fresh r2p_fresh_test r2p_fresh_e2e; do
  psql "$PG/postgres" -q -c "DROP DATABASE IF EXISTS $db WITH (FORCE);" -c "CREATE DATABASE $db;"
done
export DATABASE_URL="${PG/postgresql:/postgresql+psycopg:}/r2p_fresh"
export TEST_DATABASE_URL="${PG/postgresql:/postgresql+psycopg:}/r2p_fresh_test"
export E2E_DATABASE_URL="${PG/postgresql:/postgresql+psycopg:}/r2p_fresh_e2e"

echo "== Engine: install, lint, types, unit tests, build"
(
  cd engine
  npm ci --silent
  npm run lint
  npm run typecheck
  npm test
  npm run build
)

echo "== API: install, migrate, lint, types, tests"
(
  cd api
  uv sync --frozen -q
  uv run playwright install chromium
  uv run alembic upgrade head
  uv run alembic check
  uv run ruff check src tests migrations
  uv run ruff format --check src tests migrations
  uv run mypy
  uv run pytest --cov -q
)

echo "== Web: install, lint, tests, build"
(
  cd web
  npm ci --silent
  npm run lint
  npm test
  npm run build
)

echo "== Modal workers: lint, types, tests"
(
  cd workers/modal
  uv sync --frozen -q
  uv run ruff check .
  uv run mypy
  uv run pytest -q
)

echo "== End-to-end: every template in a real browser, then the web app"
(cd engine && CI=1 npx playwright test --reporter=line)
(cd web && CI=1 npx playwright test --reporter=line)

echo "ZIP verified: $ZIP"

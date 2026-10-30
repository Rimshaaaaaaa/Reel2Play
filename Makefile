# Reel2Play: one command per everyday task. Run `make help` for the list.
.PHONY: help setup engine db api web check lint test e2e eval build zip

help:
	@echo "make setup  install API (uv), engine and web (npm) dependencies, build the engine"
	@echo "make engine rebuild the game engine and templates (engine/dist)"
	@echo "make db     apply database migrations"
	@echo "make api    run the API on :8000 (mock models unless AI_MODE=live)"
	@echo "make web    run the web app on :5173"
	@echo "make check  lint, types, unit and integration tests, web build"
	@echo "make e2e    Playwright tests (starts its own API and web server)"
	@echo "make eval   the evaluation harness on eval/ci.json (synthetic, mock model)"
	@echo "make zip    build ../reel2play.zip without secrets or build output"

setup:
	cd api && uv sync && uv run playwright install chromium
	cd engine && npm ci && npm run build
	cd web && npm ci
	cd workers/modal && uv sync

engine:
	cd engine && npm run build

db:
	cd api && uv run alembic upgrade head

api:
	cd api && uv run uvicorn reel2play.main:app --reload --port 8000

web:
	cd web && npm run dev

lint:
	cd api && uv run ruff check src tests migrations && uv run ruff format --check src tests migrations
	cd api && uv run mypy
	cd engine && npm run lint && npm run typecheck
	cd web && npm run lint
	cd workers/modal && uv run ruff check . && uv run mypy

test: engine
	cd api && uv run pytest --cov
	cd engine && npm test
	cd web && npm test
	cd workers/modal && uv run pytest

build:
	cd web && npm run build

check: lint test build

e2e: engine
	cd engine && npx playwright test
	cd web && npx playwright test

eval:
	cd api && uv run reel2play eval run ../eval/ci.json

zip:
	python3 scripts/make_zip.py ../reel2play.zip

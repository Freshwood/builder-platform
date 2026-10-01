# Homeworking task runner (https://just.systems). Run `just` to list recipes.
set dotenv-load := true

default:
    @just --list

# Install all dependencies
install:
    uv sync
    corepack pnpm install

# Start local infrastructure (PostgreSQL)
infra:
    docker compose up -d --wait postgres

# Apply database migrations
migrate:
    uv run --package homeworking-api alembic -c apps/api/alembic.ini upgrade head

# Run API and web app in development mode
dev: infra migrate
    #!/usr/bin/env bash
    trap 'kill 0' EXIT
    uv run uvicorn homeworking.main:app --reload --port 8000 &
    corepack pnpm --filter web dev &
    wait

# Lint, format check, type check, architecture contracts
check:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    uv run lint-imports
    corepack pnpm -r lint
    corepack pnpm -r typecheck

# Python tests (SQLite) and web unit checks
test:
    uv run pytest

# Python tests including PostgreSQL integration tests
test-pg: infra
    TEST_DATABASE_URL=postgresql+psycopg://homeworking:homeworking@localhost:5433/homeworking uv run pytest

# Export OpenAPI schema and regenerate the TypeScript client
openapi:
    uv run python -m homeworking.openapi > packages/api-client/openapi.json
    corepack pnpm --filter @homeworking/api-client generate

# Browser end-to-end tests with accessibility checks (offline LLM)
e2e:
    corepack pnpm --filter web e2e

fmt:
    uv run ruff format .
    uv run ruff check --fix .
    corepack pnpm -r format

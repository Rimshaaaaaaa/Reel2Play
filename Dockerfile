# Reel2Play API for Render's free web service (Docker runtime).

# 1. Build the game engine and templates into engine/dist.
FROM node:22-slim AS engine
WORKDIR /app/engine
COPY engine/package.json engine/package-lock.json ./
RUN npm ci
COPY engine/ ./
COPY templates/ /app/templates/
RUN npm run build

# 2. The API, with ffmpeg, the engine build and the template descriptions beside it.
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/ ./
RUN uv sync --frozen --no-dev
COPY templates/ /app/templates/
COPY samples/ /app/samples/
COPY --from=engine /app/engine/dist /app/engine/dist

ENV APP_ENV=production PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn reel2play.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]

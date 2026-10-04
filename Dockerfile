# Single image: the Vite build served by FastAPI. No secrets are baked in; configure via env vars at runtime.

# --- Stage 1: frontend -------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend --------------------------------------------------------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/backend/.venv/bin:$PATH" \
    FRONTEND_DIST=/app/frontend_dist \
    PGEOCODE_DATA_DIR=/app/backend/.cache/pgeocode

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY --from=frontend /frontend/dist /app/frontend_dist

# Non-root runtime user; backend/.cache holds the search snapshot and pgeocode's GeoNames download.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/backend/.cache \
    && chown -R app:app /app/backend/.cache
USER app

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]

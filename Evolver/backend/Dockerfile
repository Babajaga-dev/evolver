# =============================================================================
#  Evolver backend — multi-stage Dockerfile basato su uv
# =============================================================================
#  - Stage 1 (builder): installa dipendenze in .venv usando uv
#  - Stage 2 (runtime): copia .venv e codice, immagine slim
# =============================================================================

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Builder
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# uv installato come binario statico
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /uvx /bin/

WORKDIR /app

# Tool di build: gcc serve per alcune wheel native (asyncpg, psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Sync dipendenze (senza il codice — sfrutta cache layer Docker)
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev || \
    uv sync --no-install-project --no-dev

# Copia codice e installa il pacchetto
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# -----------------------------------------------------------------------------
# Runtime
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Solo libpq runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 evolver \
    && useradd --uid 1000 --gid evolver --shell /bin/bash --create-home evolver

WORKDIR /app

# Copia ambiente + codice dal builder
COPY --from=builder --chown=evolver:evolver /app /app

USER evolver

# Healthcheck via curl (gestito anche da Dokploy esternamente)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

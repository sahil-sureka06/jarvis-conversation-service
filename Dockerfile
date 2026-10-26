# ── JARVIS Conversation Service — Dockerfile ────────────────────────────────
ARG PYTHON_VERSION=3.12
ARG POETRY_VERSION=1.8.3

FROM python:${PYTHON_VERSION}-slim AS builder
ARG POETRY_VERSION=1.8.3
WORKDIR /app
RUN pip install --no-cache-dir poetry==${POETRY_VERSION}
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache
COPY pyproject.toml ./
RUN poetry lock --no-update 2>/dev/null || true
RUN poetry install --only=main --no-root && rm -rf ${POETRY_CACHE_DIR}

FROM python:${PYTHON_VERSION}-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.venv /app/.venv
COPY . .
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]

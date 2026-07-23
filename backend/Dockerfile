# Production image for Railway (and similar hosts).
# sentence-transformers pulls torch; first boot downloads HuggingFace weights
# into HF_HOME (can take several minutes on a cold instance).
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY pyproject.toml uv.lock ./

# Install dependencies only — runtime imports `app.*` via PYTHONPATH (same as
# local `uvicorn app.main:app` from the backend directory).
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Railway injects PORT; default 8000 for local docker runs.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

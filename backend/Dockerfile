# Production image for Railway (portable to any container host).
#
# Sized for a host with ~1GB+ RAM, because this backend holds BOTH the
# bge-small embedder and the ms-marco cross-encoder resident. That does not
# fit the 512MB free tiers the README warns about, and keeping both loaded is
# what lets RERANK_ENABLED stay at its default `true`, so deployed ranking
# matches the local baseline exactly.
#
# torch comes from PyTorch's CPU index rather than PyPI. The PyPI linux wheel
# drags in ~43 nvidia-*/cuda-* packages (several GB) that this CPU-only host
# can never use. Same torch version, same CPU numerics — and it matches what
# the Windows dev machine already runs, where no CUDA payload exists either.
FROM python:3.11-slim-bookworm

# Run as a non-root user, and keep the model cache inside its home so the
# weights baked in below are readable at runtime.
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/opt/venv/bin:/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

RUN python -m venv /opt/venv

# torch first, from the CPU index, so the dependency install below sees it
# already satisfied and never reaches for the CUDA build.
RUN uv pip install --python /opt/venv/bin/python --no-cache \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==2.13.0"

# Mirrors backend/pyproject.toml's [project].dependencies.
RUN uv pip install --python /opt/venv/bin/python --no-cache \
      "fastapi>=0.115" \
      "uvicorn[standard]>=0.32" \
      "pymongo>=4.9" \
      "python-dotenv>=1.0" \
      "openpyxl>=3.1" \
      "sentence-transformers>=3.0" \
      "httpx>=0.27"

WORKDIR /app
COPY --chown=user:user app ./app

USER user

# Bake the weights into the image. Without this a cold start spends its first
# request downloading ~230MB from the Hub; app/main.py's background warm-up
# threads then find them already on disk.
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

EXPOSE 8000

# Railway injects PORT; 8000 is the local-docker default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

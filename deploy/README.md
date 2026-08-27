# Deployment

Deployment-only files. Nothing here is imported by the application; deleting
this directory, `backend/Dockerfile`, `backend/railway.toml`, and
`frontend/vercel.json` returns the project to a local-only setup.

- `backend/Dockerfile` — container image. Portable across container hosts; it
  honours `$PORT` and defaults to 8000.
- `backend/railway.toml` — Railway service config (Dockerfile builder,
  `/health` healthcheck).
- `frontend/vercel.json` — SPA rewrite for the Vercel static deployment.

Backend runs on Railway, frontend on Vercel, database stays on the existing
MongoDB Atlas cluster.

## Why not the free tiers

- **Hugging Face Spaces** — Docker Spaces now require a PRO subscription;
  only Static Spaces are free.
- **Render free / 512MB** — too small to hold the embedder and the
  cross-encoder at once. Fitting it would mean `RERANK_ENABLED=false`, which
  changes ranking, so it was rejected rather than degrade search behavior.

## Secrets

Set in the host's own secret store, never committed:
`MONGODB_URI`, `DB_NAME`, `CORS_ALLOW_ORIGINS`, `LLM_PROVIDER`,
`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_MAX_TOKENS`,
`LLM_TIMEOUT_SECONDS`.

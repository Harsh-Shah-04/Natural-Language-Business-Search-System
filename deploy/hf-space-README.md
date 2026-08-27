---
title: Business Search Backend
emoji: 🔎
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: FastAPI backend for natural-language business search
---

# Business Search Backend

FastAPI backend for the natural-language business search system: hybrid Atlas
vector + keyword retrieval, weighted RRF fusion, cross-encoder reranking, and
an LLM query-intent layer.

Source: https://github.com/Harsh-Shah-04/Natural-Language-Business-Search-System

## Endpoints

| Route | Purpose |
| --- | --- |
| `GET /health` | Liveness |
| `GET /health/model` | Embedder (`BAAI/bge-small-en-v1.5`) load state |
| `GET /health/reranker` | Cross-encoder load state |
| `GET /health/intent` | Query-intent provider state |
| `GET /api/filters/values` | Allowed filter values |
| `POST /api/search` | Hybrid search + inferred intent |
| `POST /api/businesses` | Register a business (embeds + stores it) |

## Configuration

Set as **Space secrets** (Settings → Variables and secrets) — never in this repo:

`MONGODB_URI`, `DB_NAME`, `CORS_ALLOW_ORIGINS`, `LLM_PROVIDER`, `LLM_BASE_URL`,
`LLM_MODEL`, `LLM_API_KEY`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`.

# Natural Language Business Search System

Semantic search over a business directory. Ask in plain English — *"eco-friendly
packaging for restaurants"*, *"someone who can defend us against computer
hacking"* — and get ranked, relevant businesses back, not keyword soup.

Built as an AI Engineer take-home. The interesting part is not that it returns
results; it's that **every ranking decision is backed by a measured evaluation**,
including the ones that didn't work.

---

## Table of contents

- [**Codebase map**](CODEBASE_MAP.md) — file-by-file map of features (start here for review)
- [Problem statement](#problem-statement)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Architecture overview](#architecture-overview)
- [Search pipeline](#search-pipeline)
- [Folder structure](#folder-structure)
- [Installation](#installation)
- [Environment variables](#environment-variables)
- [Running the backend](#running-the-backend)
- [Running the frontend](#running-the-frontend)
- [API documentation](#api-documentation)
- [Screenshots](#screenshots)
- [Evaluation results](#evaluation-results)
- [Performance metrics](#performance-metrics)
- [Deployment guide](#deployment-guide)
- [Future improvements](#future-improvements)

---

## Problem statement

A directory of 120 businesses is only useful if people can find the right one.
Keyword search fails the way users actually type:

- **Vocabulary mismatch.** A user searching *"computer hacking defense"* needs the
  business whose profile says *"cybersecurity, penetration testing, SOC"* — zero
  shared keywords.
- **Intent, not tokens.** *"a place to stay overnight during my business trip"*
  means Hotels. A keyword engine sees the word "business" and matches an
  insurance company.
- **Structured filters still matter.** "Manufacturers in Pune" is a legitimate
  narrowing that pure semantics shouldn't throw away.

So the system needs semantic understanding *and* exact-term recall *and*
structured filtering, without any one of them wrecking the others. The whole
project is an exercise in proving which combination actually ranks best rather
than assuming.

---

## Features

| Feature | What it does |
|---|---|
| **Semantic search** | Embeds the query and the business corpus into the same 384-dim vector space; matches on meaning, not tokens. |
| **Hybrid search** | Runs vector search and Atlas keyword search concurrently, fuses with Reciprocal Rank Fusion. |
| **Tuned hybrid** | Score-threshold gating on weak keyword hits, weighted RRF favouring semantics, keyword search narrowed to discriminative fields. |
| **Cross-encoder reranking** | Rescores the fused top-20 by full (query, document) attention. Toggle-able; ships on because the eval says it earns its place. |
| **Dynamic filters** | Industry / City / State / Nature / Sub Category, validated against a live allow-list derived from the DB (also closes a NoSQL-injection-shaped gap). |
| **Evaluation framework** | 30 golden queries across 6 categories, scored with Precision@K, Recall@K, MRR. Every ranking change is gated on it. |
| **Business registration** | `POST /api/businesses` embeds and stores a new business so it's searchable immediately, through the same pipeline. |
| **React interface** | Search with keyword highlighting, filters, registration form, and full loading / empty / error states. |

---

## Tech stack

**Backend** — Python 3.11+, FastAPI, Pydantic v2, PyMongo, `uv` for dependency
management.

**Search / ML** — MongoDB Atlas Vector Search (`$vectorSearch`) + Atlas Search
(`$search`, Lucene); `sentence-transformers` with
[`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) as the
bi-encoder embedder (384-dim, L2-normalized) and
[`cross-encoder/ms-marco-MiniLM-L-6-v2`](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2)
as the reranker. Both run locally on CPU, no API keys, no per-query cost.

**Frontend** — React 19, TypeScript, Vite. No UI kit, no state library, no HTTP
client — `fetch` and plain CSS keep the dependency surface minimal.

---

## Architecture overview

```mermaid
flowchart TD
    U([User]) --> FE["React Frontend<br/>Vite + TypeScript"]
    FE -->|"POST /api/search"| API["FastAPI Backend"]

    API --> EMB["Embedding Model<br/>bge-small-en-v1.5<br/>384-dim, normalized"]
    API --> FIL["Filter allow-list<br/>validated, cached"]

    EMB --> VS["Atlas Vector Search<br/>$vectorSearch (cosine)"]
    FIL -.->|"optional $match"| VS
    API --> KS["Atlas Keyword Search<br/>$search (Lucene)"]
    FIL -.->|"optional $match"| KS

    VS --> RRF["Weighted RRF<br/>vector 0.7 / keyword 0.3"]
    KS --> RRF
    RRF --> CE["Cross-Encoder Rerank<br/>ms-marco-MiniLM-L-6-v2<br/>top-20"]
    CE --> RES(["Ranked Results"])
    RES --> FE
```

Vector search and keyword search run **concurrently** (a two-worker
`ThreadPoolExecutor`), not in sequence — both feed the fusion stage. Reranking is
a strictly additive stage after fusion; if the cross-encoder fails to load or
infer, search degrades to un-reranked hybrid results rather than erroring.

**Registration write path:**

```mermaid
flowchart LR
    F["Register form"] -->|"POST /api/businesses"| V["Pydantic validation"]
    V --> E["Same embedding pipeline<br/>build_embedding_text + embed_texts"]
    E --> M[("MongoDB Atlas<br/>businesses")]
    M --> I["invalidate_filter_cache()"]
    M -.->|"Atlas index sync"| S["Searchable via /api/search"]
```

---

## Search pipeline

1. **Embed the query.** `bge-small-en-v1.5` encodes it to a 384-dim L2-normalized
   vector. The document side was embedded at ingest from
   `business_description + products_services + keywords + specialties +
   sub_category` — contact fields are excluded because they carry no semantic
   signal.
2. **Validate filters.** Any supplied filter value is checked against a live
   allow-list of actual DB values. Anything outside it is rejected with `422`,
   never passed through as a raw query clause.
3. **Retrieve, concurrently.**
   - `$vectorSearch` over the `embedding` field (cosine).
   - `$search` over `keywords`, `specialties`, `products_services` — deliberately
     narrowed; `business_description` carries templated boilerplate that produced
     coincidental matches.
   - Weak keyword hits are dropped before fusion (must score ≥30% of the query's
     own top keyword score — Atlas `searchScore` has no fixed cross-query scale,
     so the threshold is relative).
4. **Fuse with weighted RRF.** `score = Σ weight / (60 + rank)`, with vector
   weighted `0.7` and keyword `0.3`. Rank-based fusion is scale-free, which is
   why it can combine two incomparable scoring systems at all. Results are tagged
   `matched_via`: `semantic`, `keyword`, or `both`.
5. **Rerank the top 20.** The cross-encoder scores each `(query, document)` pair
   with full attention, so it judges relevance directly instead of by vector
   distance. Fusion deliberately returns a *wider* pool than the requested limit
   so a candidate ranked #15 can climb into the top 10.
6. **Return the top N.**

**Why each stage exists** is documented with the evaluation that justified it —
see [Evaluation results](#evaluation-results). The short version: hybrid alone
scored *worse* than vector-only, tuning recovered about half the gap, and
reranking closed the rest.

---

## Folder structure

```
.
├── README.md                     # this file
├── design-doc.md                 # initial design
├── design-doc-v2.md              # revised design (source of truth for decisions)
├── roadmap.md                    # milestone plan
├── Business_..._120_Companies.xlsx   # source dataset
│
├── backend/
│   ├── README.md                 # deep backend documentation
│   ├── pyproject.toml            # deps (uv)
│   ├── .env.example
│   ├── app/
│   │   ├── main.py               # FastAPI app, routes, CORS, model warm-up
│   │   ├── search.py             # hybrid retrieval + weighted RRF + rerank hook
│   │   ├── embeddings.py         # bi-encoder singleton, build_embedding_text
│   │   ├── reranker.py           # cross-encoder singleton + rerank_candidates
│   │   ├── registration.py       # business registration write path
│   │   ├── filters.py            # live filter allow-list + cache invalidation
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── db.py                 # Mongo client singleton
│   │   └── constants.py          # model names, embedding dimensions
│   ├── scripts/
│   │   ├── seed.py               # xlsx ingest + embedding backfill
│   │   ├── eval.py               # golden-query evaluation harness
│   │   ├── eval_dataset.py       # 30 golden queries + relevance judgments
│   │   ├── create_atlas_indexes.py
│   │   ├── verify_atlas_spike.py
│   │   └── atlas_indexes/        # index definitions (JSON)
│   └── eval_reports/             # generated evaluation reports
│
└── frontend/
    ├── README.md
    ├── package.json
    ├── .env.example
    └── src/
        ├── api/                  # HTTP client + typed endpoint functions
        ├── types/                # API contract types (mirror schemas.py)
        ├── hooks/                # useSearch, useFilterOptions, useRegistrationForm
        ├── components/           # SearchBar, FilterPanel, ResultCard, ...
        ├── pages/                # SearchPage, RegisterPage
        ├── utils/highlight.tsx   # XSS-safe keyword highlighting
        ├── App.tsx               # shell: nav + view switch
        └── index.css             # single organized stylesheet
```

---

## Installation

**Prerequisites:** Python 3.11+, Node `^20.19` or `>=22.12` (required by Vite 8),
a MongoDB Atlas cluster (the free M0 tier is enough), and
[`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Harsh-Shah-04/Natural-Language-Business-Search-System.git
cd Natural-Language-Business-Search-System
```

**Backend:**

```bash
cd backend
uv sync                                  # install dependencies
cp .env.example .env                     # then fill in MONGODB_URI
uv run python scripts/create_atlas_indexes.py   # create both Atlas indexes
uv run python scripts/seed.py                   # ingest 120 businesses + embeddings
```

The first run downloads the models (~135MB embedder, ~92MB reranker) from
Hugging Face and caches them locally.

**Frontend:**

```bash
cd ../frontend
npm install
```

---

## Environment variables

**`backend/.env`**

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MONGODB_URI` | **yes** | — | Atlas connection string. Never commit this. |
| `DB_NAME` | no | `business_search` | Database name. |
| `CORS_ALLOW_ORIGINS` | no | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allow-list of frontend origins. |
| `RERANK_ENABLED` | no | `true` | Set `false` to disable cross-encoder reranking (faster, slightly less precise). |

**`frontend/.env.local`**

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | no | `http://127.0.0.1:8000` | Base URL of the backend API. |

---

## Running the backend

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Serves on `http://127.0.0.1:8000`. Interactive API docs at `/docs`.

Models load in **background threads** at startup, so the API is reachable
instantly and no live request eats a cold model load. Check readiness:

```bash
curl http://127.0.0.1:8000/health           # {"status":"ok"}
curl http://127.0.0.1:8000/health/model     # embedder
curl http://127.0.0.1:8000/health/reranker  # cross-encoder
```

Run the evaluation harness (requires a seeded cluster):

```bash
uv run python scripts/eval.py
```

## Running the frontend

The backend must be running first, with CORS allowing the frontend origin (the
default config already allows the Vite dev server).

```bash
cd frontend
npm run dev        # http://localhost:5173
npm run build      # type-check (tsc -b) + production build
npm run preview    # serve the production build
npm run lint       # oxlint
```

---

## API documentation

Base URL: `http://127.0.0.1:8000`

> **Note on method:** search is `POST /api/search`, not `GET`. The query,
> `limit`, and the nested `filters` object are a structured JSON body, which is
> awkward to express as query parameters. This documents the implemented
> contract.

### `POST /api/search`

Hybrid semantic + keyword search with optional filters and cross-encoder
reranking.

**Body parameters**

| Field | Type | Required | Constraints | Default |
|---|---|---|---|---|
| `query` | string | yes | 1–500 chars, not blank after trim | — |
| `limit` | integer | no | 1–50 | `10` |
| `filters` | object \| null | no | see below | `null` |
| `filters.industry` | string \| null | no | must be a known value | `null` |
| `filters.city` | string \| null | no | must be a known value | `null` |
| `filters.state` | string \| null | no | must be a known value | `null` |
| `filters.nature` | string \| null | no | must be a known value | `null` |
| `filters.sub_category` | string \| null | no | must be a known value | `null` |

**Example request**

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "eco friendly packaging for restaurants",
    "limit": 3,
    "filters": {"state": "Maharashtra"}
  }'
```

**Example response** `200 OK`

```json
{
  "query": "eco friendly packaging for restaurants",
  "results": [
    {
      "id": "68c1f0a2b3d4e5f6a7b8c9d0",
      "business_name": "Prime Food Solutions",
      "nature": "Goods",
      "industry": "Manufacturing",
      "sub_category": "Food Packaging",
      "city": "Mumbai",
      "state": "Maharashtra",
      "contact_person": "…",
      "email": "…",
      "website": "…",
      "phone": "…",
      "business_description": "…",
      "products_services": "…",
      "keywords": "…",
      "specialties": "…",
      "score": -0.944,
      "matched_via": "both"
    }
  ],
  "filters": {"state": "Maharashtra", "industry": null, "city": null, "nature": null, "sub_category": null}
}
```

`score` is the cross-encoder relevance logit when reranking is on (it can be
negative — that is expected and comparable *within* a result set), or the fused
RRF score when reranking is off. `matched_via` is `semantic`, `keyword`, or
`both`.

**Error codes**

| Code | When |
|---|---|
| `422` | Blank/missing/oversized `query`, `limit` out of range, or a filter value not in the live allow-list. |
| `503` | Embedding model or Atlas unavailable. |

---

### `POST /api/businesses`

Register a new business. Embeds it with the same pipeline used at ingest and
stores it, so it becomes searchable through `/api/search`.

**Body parameters**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `business_name` | string | **yes** | 1–200 chars, unique |
| `industry` | string | **yes** | 1–100 chars |
| `nature` | string | **yes** | 1–100 chars |
| `sub_category` | string | **yes** | 1–100 chars |
| `business_description` | string | **yes** | 1–5000 chars |
| `products_services` | string | **yes** | 1–5000 chars |
| `city` | string | **yes** | 1–100 chars |
| `state` | string | **yes** | 1–100 chars |
| `keywords` | string | no | ≤1000 chars |
| `address` | string | no | ≤500 chars |
| `phone` | string | no | ≤50 chars |
| `email` | string | no | ≤200 chars, email format |
| `website` | string | no | ≤300 chars, URL format |

Blank optional fields are normalised to absent.

**Example request**

```bash
curl -X POST http://127.0.0.1:8000/api/businesses \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "Acme Cold Chain",
    "industry": "Logistics",
    "nature": "Services",
    "sub_category": "Cold Storage",
    "business_description": "Refrigerated warehousing and last-mile cold delivery.",
    "products_services": "Cold storage, refrigerated transport",
    "city": "Pune",
    "state": "Maharashtra",
    "email": "hello@acmecold.example",
    "website": "acmecold.example"
  }'
```

**Example response** `201 Created`

```json
{ "id": "68c1f0a2b3d4e5f6a7b8c9d1", "business_name": "Acme Cold Chain" }
```

**Error codes**

| Code | When |
|---|---|
| `409` | A business with that `business_name` already exists (unique index). |
| `422` | Missing/blank required field, or malformed `email` / `website`. |
| `503` | Embedding model or database unavailable. |

> Searchability is immediate in practice (observed ~1s in testing) but depends on
> Atlas index sync, which is eventually consistent — not a transactional
> guarantee.

---

### `GET /api/filters/values`

The allowed values for each filterable field, derived from the live database
(not a seed-time snapshot). Backs the frontend dropdowns and the `422` validation
on `/api/search`. Cached in-process; invalidated automatically when a business is
registered.

**Parameters:** none.

**Example request**

```bash
curl http://127.0.0.1:8000/api/filters/values
```

**Example response** `200 OK`

```json
{
  "industry": ["Agriculture", "Construction", "…"],
  "city": ["Ahmedabad", "Bengaluru", "…"],
  "state": ["Delhi", "Gujarat", "…"],
  "nature": ["Goods", "Services"],
  "sub_category": ["AI Solutions", "Advertising", "…"]
}
```

**Error codes:** `503` if the database is unavailable.

---

### `GET /health`

Liveness probe. Returns immediately regardless of model state.

```bash
curl http://127.0.0.1:8000/health
```

```json
{ "status": "ok" }
```

**Error codes:** none under normal operation.

---

### `GET /health/model`

Readiness of the **embedding model**. Search cannot serve results until this is
`ready`.

```bash
curl http://127.0.0.1:8000/health/model
```

```json
{ "status": "ready" }
```

`status` is one of `not_started`, `loading`, `ready`, `error`. On `error` a
`detail` field carries the load failure message.

---

### `GET /health/reranker`

Readiness of the **cross-encoder reranker**, reported independently of the
embedder because the two load separately and search still works (un-reranked) if
this one is down. Reports `not_started` when `RERANK_ENABLED=false`.

```bash
curl http://127.0.0.1:8000/health/reranker
```

```json
{ "status": "ready" }
```

Same status values and `detail` behaviour as `/health/model`.

---

## Screenshots

Screenshots are **not yet captured**. The placeholders below are the intended
set; capture instructions follow.

| View | Placeholder |
|---|---|
| Search page (idle state) | `docs/screenshots/search-page.png` |
| Search results with keyword highlighting | `docs/screenshots/search-results.png` |
| Filters applied | `docs/screenshots/filters.png` |
| Registration page | `docs/screenshots/registration.png` |
| Responsive mobile view | `docs/screenshots/responsive-mobile.png` |

**How to capture them**

1. Start the backend (`uv run uvicorn app.main:app --reload`) and the frontend
   (`npm run dev`), then open `http://localhost:5173`.
2. **Search page** — capture the idle state before searching.
3. **Search results** — search `eco friendly packaging for restaurants`; the
   matched terms render highlighted inside the cards.
4. **Filters** — with results on screen, set *State* to a real value and capture
   the narrowed result set.
5. **Registration** — switch to the Register tab; capture the grouped form
   (Business Information / Location / Contact Information).
6. **Responsive** — open DevTools device toolbar at ~390px width and capture the
   single-column layout with the full-width nav.
7. Save each PNG to `docs/screenshots/` using the filenames above; the table
   links resolve once they exist.

See [`docs/screenshots/README.md`](docs/screenshots/README.md) for the same
checklist next to the files.

---

## Evaluation results

30 golden queries across 6 categories (semantic, keyword-heavy, synonym,
multi-intent, filtered, edge cases), with hand-verified relevance judgments.
Scored with Precision@K, Recall@K and MRR. Full report:
[`backend/eval_reports/`](backend/eval_reports/); regenerate with
`uv run python scripts/eval.py`.

| System | P@5 | P@10 | R@5 | R@10 | MRR |
|---|---|---|---|---|---|
| Vector-only | 0.560 | 0.303 | 0.946 | 1.000 | **0.958** |
| Previous Hybrid | 0.467 | 0.283 | 0.792 | 0.940 | 0.863 |
| Tuned Hybrid | 0.513 | 0.303 | 0.875 | 1.000 | 0.869 |
| **Hybrid + Cross-Encoder** | **0.560** | **0.303** | **0.946** | **1.000** | 0.929 |

**What the numbers actually say**

- **Naive hybrid made things worse.** Adding keyword search *dropped* P@5 from
  0.560 to 0.467. Root cause, verified by inspection: Atlas `$search` matching a
  single coincidental token with no real relevance (query *"computer hacking
  defense"* matched an AI-solutions firm on the word "computer"), which
  rank-based RRF had no way to discount.
- **Tuning recovered about half.** Score-gating, weighted RRF and field narrowing
  took P@5 to 0.513 and R@10 back to 1.000. Genuine improvement, not a full fix.
- **Reranking closed the rest.** P@5 0.513 → 0.560 and R@5 0.875 → 0.946, both now
  equal to vector-only; MRR 0.869 → 0.929. The two categories tuning couldn't
  touch improved exactly as predicted: `synonym` P@5 0.480 → 0.560, `edge_case`
  MRR 0.722 → 1.000.

**Honest caveat.** On this small, clean, templated 120-document set, vector-only
is already very strong, so reranking brings hybrid *to parity* rather than
strictly beating it everywhere — vector-only's MRR (0.958) still edges the
reranked pipeline (0.929). The win is getting keyword-exact recall *and* semantic
precision together; on a messier corpus that's where the combination would pull
clearly ahead. Reranking ships enabled because it measurably improves precision@5
over the best non-reranked system, which was the pre-registered bar.

---

## Performance metrics

Benchmarked on a local CPU machine against the live Atlas cluster, warm models.

**Search latency**

| Config | p50 | p95 |
|---|---|---|
| Hybrid (rerank off) | ~58ms | ~800ms |
| Hybrid + cross-encoder | ~463ms | ~830ms |

Reranking costs **~+405ms p50** — running the cross-encoder over ~20
`(query, document)` pairs on CPU. That lands just under the 500ms p50 target but
with little headroom; `RERANK_ENABLED=false` gives back the fast path instantly.
The ~800ms p95 appears on both rows and is cold-cache / Atlas round-trip noise,
not reranking.

> **These absolute numbers are point-in-time, single-machine, and not
> reproducible on demand.** Re-measuring the identical code in a later session
> (same commit, verified byte-identical) gave ~178ms p50 without reranking and
> ~2135ms with it — roughly 3-5x higher across *both* paths, including the path
> that never touches the cross-encoder. The cause is machine state (CPU
> contention, thermal, Atlas network), not a regression. Treat the **relative**
> finding as the durable one: reranking dominates search latency and costs
> several times the retrieval-and-fusion path. If you benchmark this yourself,
> expect your own absolute figures and compare rerank-on against rerank-off on
> the *same* machine in the *same* session.

**Filtering** is effectively free at this corpus size: unfiltered p50 ~72ms,
filtered-by-city ~68ms, filtered-by-two-fields ~67ms.

**Embedding throughput:** model load ~6.4s, encoding all 120 business documents
~3.8s (~31 docs/sec), single-query encode ~37ms.

**Memory:** embedder ~135MB on disk; cross-encoder ~92MB on disk / 22.7M params,
cold load ~8.5s. A rerank-enabled process holds **both** models — the main
constraint for small free-tier hosts.

---

## Deployment guide

Not yet deployed; this is the intended path.

**Backend (Render / Railway / Fly.io)**

- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Set `MONGODB_URI`, `DB_NAME`, and `CORS_ALLOW_ORIGINS` (the deployed frontend
  origin) as environment variables.
- Allow the host's outbound IPs in the Atlas Network Access list.
- Run `scripts/create_atlas_indexes.py` and `scripts/seed.py` once against the
  target cluster before first use.

**Frontend (Vercel / Netlify)**

- Build command `npm run build`, output directory `dist`, root `frontend/`.
- Set `VITE_API_BASE_URL` to the deployed backend URL. Vite inlines env vars at
  **build** time, so changing it requires a rebuild, not just a restart.

**Production considerations**

- **Memory is the binding constraint.** Both models resident is tight on a 512MB
  free tier. Either size up or set `RERANK_ENABLED=false` — the toggle exists
  precisely for this trade.
- **Cold starts.** Models load in background threads at startup, but a
  scale-to-zero host pays that load on the first request after a spin-up. Prefer
  an always-on instance, and use `/health/model` and `/health/reranker` as
  readiness signals.
- **CORS.** `CORS_ALLOW_ORIGINS` is an explicit allow-list — set it to the real
  frontend origin, not `*`.
- **Secrets.** `MONGODB_URI` belongs in the host's secret store. `backend/.env`
  is gitignored and must stay that way.
- **No auth.** Every endpoint is public, including `POST /api/businesses`. A
  public deployment needs auth and rate limiting before it accepts real writes.

---

## Future improvements

- **Fix the residual ranking collision.** A query token that matches a business's
  own discriminative field in a *different sense* (the word "business" in
  "business trip" vs "business insurance") still misleads keyword retrieval when
  it's the only hit. Reranking recovers most of these; query-side sense
  disambiguation would attack the cause.
- **Filter at the index, not after it.** `$vectorSearch` truncates internally
  before `$match`, so filtered searches over-fetch (pool widened to 200). At a
  larger corpus this needs Atlas native filter fields that pre-filter before the
  HNSW traversal.
- **Automated tests.** The project is verified by the evaluation harness and live
  manual verification; it has no unit/integration test suite. That's the biggest
  engineering gap.
- **Auth + rate limiting**, needed before any public write endpoint.
- **Pagination** — the API caps at 50 results with no cursor.
- **Grow the golden set.** 30 queries over 120 documents is enough to make
  directional calls, not enough for tight confidence intervals. More queries and
  multiple judges would harden every conclusion above.
- **Deployment**, per the guide above.

---

## Documentation map

| Document | Contents |
|---|---|
| `README.md` | This overview. |
| [`docs/PROJECT_SUMMARY.md`](docs/PROJECT_SUMMARY.md) | Condensed summary: features, stack, results, limitations. Start here for a quick read. |
| [`docs/SUBMISSION.md`](docs/SUBMISSION.md) | Submission checklist and the final end-to-end QA results. |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | 3-5 minute demo walkthrough. |
| [`backend/README.md`](backend/README.md) | Deep backend documentation: embedding pipeline, index definitions, tuning rationale, benchmarks. |
| [`frontend/README.md`](frontend/README.md) | Frontend structure and scripts. |
| [`design-doc-v2.md`](design-doc-v2.md) | Architecture decisions and the evidence rules ranking changes were gated on. |
| [`roadmap.md`](roadmap.md) | Milestone plan and test criteria. |

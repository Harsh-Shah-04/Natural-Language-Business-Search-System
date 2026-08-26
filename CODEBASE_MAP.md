# Codebase Map

One-page guide to this take-home: **what each part does**, **which feature it supports**, and **where to look first**.

> Start here if you are reviewing the repo. For setup and eval numbers, use `README.md`. For deep design rationale, use `design-doc-v2.md`.

---

## Product features → code

| Feature | What the user gets | Primary code |
|---|---|---|
| **Natural-language search** | Type a query → ranked businesses | `backend/app/search.py`, `frontend/src/pages/SearchPage.tsx` |
| **Semantic (vector) retrieval** | Match by meaning, not shared keywords | `embeddings.py` + Atlas `$vectorSearch` in `search.py` |
| **Keyword retrieval** | Exact / near-term Lucene matches | Atlas `$search` in `search.py` + `scripts/atlas_indexes/search_index.json` |
| **Hybrid fusion (RRF)** | Merge vector + keyword lists | `_reciprocal_rank_fusion()` in `search.py` |
| **Cross-encoder rerank** | Rescore top candidates for precision | `reranker.py` (toggle: `RERANK_ENABLED`, policy: `RERANK_POLICY`) |
| **Query understanding** | Describe a situation → system infers the service need | `intent.py`, `llm.py`, `taxonomy.py` |
| **Visible reasoning** | *"I understood you need…"* panel with provenance | `IntentPanel.tsx`, `intent` field in `schemas.py` |
| **Negation / exclusions** | *"I don't want X"* removes that category from results | `taxonomy.resolve_categories()` → `$nin` in `search.py` |
| **Intent-aware expansion** | Symptom wording widened with taxonomy vocabulary | `search_with_intent()` in `search.py` |
| **Intent cache** | Repeat queries answer instantly and identically | `_cache_get/_cache_put` in `intent.py` |
| **Filters** | Industry / City / State / Nature / Sub Category | `filters.py`, `FilterPanel.tsx` |
| **Business registration** | Add a business → immediately searchable | `registration.py`, `RegisterPage.tsx` |
| **Exact name lookup** | Find a business by its registered name | `business_name` in embed text + keyword paths + Atlas mapping |
| **Evaluation** | Prove ranking changes with metrics | `scripts/eval.py`, `scripts/eval_dataset.py`, `eval_reports/` |
| **API** | HTTP contract for search / filters / register | `main.py`, `schemas.py` |

---

## Repository layout (top level)

```
Intern_assignment/
├── README.md                 # Setup, architecture, eval results, deploy notes
├── CODEBASE_MAP.md           # This file — navigation map
├── design-doc.md             # Early design notes
├── design-doc-v2.md          # Final design (evidence-gated decisions)
├── roadmap.md                # Milestone plan (M1–M5)
├── Business_Matchmaking_…xlsx # Source dataset (120 companies)
├── docs/                     # Submission / demo extras
├── backend/                  # FastAPI + ML + MongoDB Atlas
└── frontend/                 # React + TypeScript + Vite UI
```

---

## Backend map (`backend/`)

### App package — `backend/app/`

| File | Role | Features |
|---|---|---|
| `main.py` | FastAPI app, CORS, lifespan warm-up, routes | Wires search, filters, registration, health |
| `schemas.py` | Pydantic request/response models | Validates search + registration (Nature = Goods/Services) |
| `db.py` | MongoDB client singleton | Shared DB access |
| `constants.py` | Model names + embedding dims | Single source for ML config |
| `embeddings.py` | Load BGE bi-encoder; `build_embedding_text`; `embed_texts` | Semantic search + registration embeddings |
| `search.py` | Hybrid pipeline (vector ∥ keyword → RRF → conditional rerank) + `search_with_intent()` | Core ranking; exclusions; expansion |
| `intent.py` | `QueryIntent` + provider chain (llm → fixture → classifier) + cache | Query understanding |
| `llm.py` | Vendor-neutral chat client over `httpx` (Anthropic / OpenAI-compatible) | LLM access, no SDK |
| `taxonomy.py` | Trusted 40-category taxonomy; `is_known_category()`, `resolve_categories()` | Security gate + exclusion mapping |
| `taxonomy.json` | Generated from the seed dataset — **never** from the DB | Prompt-injection boundary |
| `intent_fixtures.json` | Checked-in demo intents, always labelled `source: fixture` | Offline demo path |
| `reranker.py` | Cross-encoder load + `rerank_candidates` | Precision boost after fusion |
| `filters.py` | Cached allow-list; validate filter values | Safe, dynamic filters |
| `registration.py` | Embed + insert new business; invalidate filter cache | Registration → searchable |

### HTTP routes (in `main.py`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Process up |
| `GET` | `/health/model` | Embedder status |
| `GET` | `/health/reranker` | Reranker status |
| `GET` | `/health/intent` | Intent layer state, active provider, `llm_error` |
| `GET` | `/api/filters/values` | Dropdown options |
| `POST` | `/api/search` | Hybrid search |
| `POST` | `/api/businesses` | Register business |

### Scripts — `backend/scripts/`

| File | Role |
|---|---|
| `seed.py` | Ingest Excel → Mongo + embeddings |
| `create_atlas_indexes.py` | Create/update Atlas vector + search indexes |
| `atlas_indexes/vector_index.json` | Vector Search index definition |
| `atlas_indexes/search_index.json` | Lucene search fields (includes `business_name`) |
| `reembed_businesses.py` | Recompute embeddings after embed-text changes |
| `eval.py` | Run golden-query evaluation (P@K, R@K, MRR) |
| `eval_dataset.py` | 30 labeled queries across 6 categories |
| `verify_atlas_spike.py` | Early Atlas connectivity / index smoke check |
| `build_taxonomy.py` | Generate `app/taxonomy.json` from the seed dataset (asserts the per-category invariant) |
| `test_contextual_search.py` | End-to-end suite: positive, negation, unmappable negation, keyword, symptom |
| `measure_intent.py` | Classifier accuracy + the evidence for its similarity gate |
| `measure_intent_determinism.py` | Repeatability: N identical calls per query, agreement + hallucination check |
| `measure_intent_expansion.py` | Five expansion arms (raw / prose / taxonomy / combined), both query classes |
| `measure_expansion_retrieval.py` | Is BM25 still worth keeping after expansion? vector vs hybrid matrix |
| `measure_rerank_policy.py` | `always` vs `never` vs `intent-gated`, both query classes |
| `measure_situational_baseline.py` | Symptom-query benchmark (the golden set cannot measure this class) |
| `compute_metric_ceiling.py` | Proves the golden set sits at 97.7% of its mathematical maximum |
| `intent_cache.py` | File-backed intent cache **for measurement scripts** — one LLM call per unique query, ever |

### Other backend files

| Path | Role |
|---|---|
| `pyproject.toml` / `uv.lock` | Python deps (`uv`) |
| `.env.example` | `MONGODB_URI`, `DB_NAME`, CORS, and the optional `LLM_*` / `INTENT_*` / `RERANK_*` block |
| `README.md` | Backend-focused setup and milestone notes |
| `eval_reports/` | Saved evidence for every ranking choice — see below |

### Evidence files — `backend/eval_reports/`

| File | What it proves |
|---|---|
| `report_*.md` | Golden-set evaluation, 4 systems (vector / hybrid / tuned / reranked) |
| `baseline_situational_20260825.md` | Symptom-query baseline; the metric-ceiling and QA-pollution findings |
| `situational_baseline.json` | Per-query symptom results, rerank on vs off |
| `intent_determinism.json` | 100 identical calls: categories stable, prose is not |
| `intent_expansion.json` | Five expansion arms across both query classes |
| `expansion_retrieval.json` | Vector vs hybrid after expansion (why BM25 stays) |
| `rerank_policy.json` | The three reranking policies |
| `intent_cache.json` | Cached LLM intents, so measurements re-run at zero API cost |

---

## Frontend map (`frontend/`)

### Entry & shell

| File | Role |
|---|---|
| `index.html` | HTML shell |
| `src/main.tsx` | React mount |
| `src/App.tsx` | Search ↔ Register view switch (no router) |
| `src/index.css` | All styles |

### Pages

| File | Feature |
|---|---|
| `src/pages/SearchPage.tsx` | Search UI: query, filters, results |
| `src/pages/RegisterPage.tsx` | Registration form + success actions |

### API client

| File | Role |
|---|---|
| `src/api/client.ts` | Base URL, `fetch`, error normalization |
| `src/api/search.ts` | `POST /api/search`, filter values |
| `src/api/businesses.ts` | `POST /api/businesses` |
| `src/types/api.ts` | TypeScript types mirroring backend schemas |

### Hooks

| File | Role |
|---|---|
| `src/hooks/useSearch.ts` | Search state, run query, loading/error |
| `src/hooks/useFilterOptions.ts` | Load filter dropdowns |
| `src/hooks/useRegistrationForm.ts` | Form values, validation, submit |

### Components

| File | Role |
|---|---|
| `SearchBar.tsx` | Query input + submit |
| `FilterPanel.tsx` / `FilterSelect.tsx` | Filter dropdowns |
| `IntentPanel.tsx` | *"I understood you need…"* — inferred need, category chips, exclusions, provenance |
| `ResultsList.tsx` / `ResultCard.tsx` | Result cards, scores, matched_via (plain text — highlighting was removed) |
| `StatusMessage.tsx` | Empty / loading / error messages |
| `FormField.tsx` | Text / textarea / select for registration |

### Frontend config

| File | Role |
|---|---|
| `package.json` | Scripts: `dev`, `build`, `lint` |
| `vite.config.ts` | Vite + React plugin |
| `.env.example` | `VITE_API_BASE_URL` (points at backend) |

---

## Docs map (`docs/` + design)

| File | Audience | Contents |
|---|---|---|
| `README.md` | Reviewer / engineer | Full project guide |
| `design-doc-v2.md` | Reviewer | Final architecture + evidence gates |
| `design-doc.md` | Context | Earlier design iteration |
| `roadmap.md` | Context | Milestone checklist |
| `docs/SUBMISSION.md` | Submission checklist | What to turn in |
| `docs/DEMO_SCRIPT.md` | Demo walkthrough | Live demo steps |
| `docs/PROJECT_SUMMARY.md` | Short overview | Elevator + stack |
| `docs/screenshots/README.md` | Screenshot capture guide | UI evidence |
| `docs/designs/contextual-intent-search.md` | Reviewer / engineer | The M6 design: problem, approaches considered, decision log |
| `docs/MEETING_STUDY_BRIEF.md` | Context | Prep notes for the review conversation |
| `CODEBASE_MAP.md` | Reviewer | This file |

---

## Search pipeline (mental model)

```
Query
  │
  ├─→ INTENT (llm → fixture → classifier, cached)
  │      ├─ service_categories ─→ taxonomy vocabulary ─┐
  │      └─ exclusions ─→ resolve_categories() ─→ $nin │
  │                                                     │
  ▼                                                     ▼
raw query + taxonomy vocabulary            (applied to both arms)
  ├─→ embed (bge-small) ──→ Atlas $vectorSearch ──┐
  │                                                ├─→ Weighted RRF fusion
  └─→ Atlas $search (name + keywords + …) ─────────┘
                         │
                         ▼
          rerank ONLY if the query names a service
                         │
                         ▼
       top N results (+ filters if set) + intent for display
```

**Trust boundary:** the taxonomy is generated from the checked-in seed dataset,
never from the database — `POST /api/businesses` is unauthenticated, so a
collection-derived taxonomy would let a stranger put text in every user's LLM
prompt. Every category a model returns is re-checked with `is_known_category()`.

**Name lookup note:** `business_name` is in embedding text, keyword paths, and the Atlas search index so registered businesses are findable by exact name even when the description does not repeat the name.

---

## Config a reviewer should know

| Variable | Where | Meaning |
|---|---|---|
| `MONGODB_URI` / `DB_NAME` | `backend/.env` | Atlas connection |
| `RERANK_ENABLED` | `backend/.env` (optional, default true) | Kill switch for the cross-encoder; wins over the policy |
| `RERANK_POLICY` | optional, default `intent-gated` | `intent-gated` \| `always` \| `never` — rerank only queries that name a service |
| `INTENT_PROVIDER` | optional, default `auto` | `auto` (llm → fixture → classifier), `llm`, `embedding`, `fixture`, `off` |
| `INTENT_EXPANSION_ENABLED` | optional, default `true` | Widen retrieval with the inferred categories' taxonomy vocabulary |
| `INTENT_CACHE_SIZE` / `INTENT_CACHE_TTL_SECONDS` | optional, `512` / `3600` | Bounds on the in-process intent cache |
| `LLM_API_KEY` | `backend/.env` (optional) | **Absent = no LLM, not an error.** Never commit it. |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL` | optional | `anthropic` or `openai`-compatible; verified against DeepSeek by config alone |
| `LLM_MAX_TOKENS` / `LLM_TIMEOUT_SECONDS` | optional, `400` / `6` | **Raise to ~1500 / 45 for reasoning models** |
| `CORS_ALLOW_ORIGINS` | `backend/.env` (optional) | Frontend origins |
| `VITE_API_BASE_URL` | `frontend/.env` | Backend URL for the UI |

---

## What is intentionally *not* in the repo

| Item | Why excluded |
|---|---|
| `.env` / secrets | Local only (gitignored) |
| `node_modules/`, `.venv/` | Installable deps |
| `.gstack/`, QA screenshots | Local agent/QA tooling, not assignment deliverables |
| Excel lock files (`~$*`) | Transient Office locks |

---

## Suggested reading order (15–20 min)

1. This file (`CODEBASE_MAP.md`) — orientation  
2. `README.md` — features, architecture diagram, how to run  
3. `backend/app/search.py` — ranking heart  
4. `backend/app/embeddings.py` + `reranker.py` — ML pieces  
5. `frontend/src/pages/SearchPage.tsx` + `RegisterPage.tsx` — UI  
6. `eval_reports/` + `scripts/eval_dataset.py` — evidence for ranking choices  
7. `design-doc-v2.md` — why hybrid + rerank shipped  

---

## Quick run (local)

```powershell
# Backend (from backend/)
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# Frontend (from frontend/)
# set VITE_API_BASE_URL=http://127.0.0.1:8001 in frontend/.env
npm run dev
```

Open http://localhost:5173 — search and register.
